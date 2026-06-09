import asyncio
import os
import datetime
import requests
import re
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

# --- CONFIGURATION ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_API")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
BASE_URL = "https://www.avito.ma/fr/maroc/voitures_d_occasion-%C3%A0_vendre?price=-40000"
MAX_PAGES = 30

# Vérification des variables d'environnement
print(f"🔍 Vérification des configurations:")
print(f"TELEGRAM_TOKEN: {'✅ Présent' if TELEGRAM_TOKEN else '❌ MANQUANT'}")
print(f"TELEGRAM_CHAT_ID: {'✅ Présent' if TELEGRAM_CHAT_ID else '❌ MANQUANT'}")
print(f"BASE_URL: {BASE_URL}")
print("-" * 50)

if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
    print("❌ ERREUR: Variables d'environnement Telegram manquantes!")
    print("   Vérifiez votre fichier .env")
    exit(1)

def extract_car_name(text):
    """Extrait correctement le nom de la voiture"""
    # Nettoie le texte
    text = text.strip()
    
    # Enlève les patterns d'icônes et de temps
    patterns_to_remove = [
        r'ClockOutline\s*Icon?i?l?\s*y?\s*a?\s*',  # Enlève "ClockOutline Iconil y a"
        r'ClockOutline\s*Icon?\s*\d*\s*',          # Enlève "ClockOutline Icon"
        r'il y a\s*\d+\s*\w+',                     # Enlève "il y a 42 min"
        r'\d+\s*(min|heure|jour|mois|an)s?',       # Enlève "42 min", "2 heures", etc.
        r'^\s*[\d\s]*$',                           # Enlève les lignes vides ou juste chiffres
        r'Iconil y a\s*\d*',                       # Enlève "Iconil y a 42"
        r'Iconi\s*\d*',                            # Enlève "Iconi"
        r'Icon\s*\d*',                             # Enlève "Icon"
    ]
    
    for pattern in patterns_to_remove:
        text = re.sub(pattern, '', text, flags=re.IGNORECASE)
    
    # Sépare par ligne et prend la première ligne non vide
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    
    # Cherche une ligne qui ressemble à un nom de voiture
    for line in lines:
        # Évite les noms d'utilisateurs (courts ou avec @)
        if len(line) < 3 or '@' in line or line.startswith('+'):
            continue
        
        # Si la ligne contient des mots comme "diesel", "km", c'est probablement un détail
        if re.search(r'(diesel|essence|km|cv|ch)', line, re.IGNORECASE):
            continue
        
        # Si la ligne contient une année, c'est peut-être le nom
        if re.search(r'(19|20)\d{2}', line):
            # Nettoie l'année du nom si présente
            line = re.sub(r'\s*(19|20)\d{2}\s*', ' ', line)
            line = line.strip()
            if line and len(line) > 2:
                return line[:40]
        
        # Si la ligne a une longueur raisonnable (entre 3 et 40 caractères)
        if 3 <= len(line) <= 40:
            return line[:40]
    
    # Si rien n'est trouvé, retourne le premier mot significatif
    words = re.findall(r'\b[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ\s-]{2,}\b', text)
    if words:
        return words[0][:40]
    
    return "Voiture"

def clean_km_value(text):
    """Nettoie la valeur du kilométrage"""
    # Cherche un nombre suivi de km
    match = re.search(r'(\d[\d\s]*)\s*kms?', text, re.IGNORECASE)
    if match:
        km = match.group(1).replace(' ', '')
        # Enlève les chiffres en trop (ex: 2014246 -> 246 ou 14246)
        if len(km) > 5 and km.startswith('20'):
            # Essayer d'extraire le vrai kilométrage
            if len(km) == 7 and km[2:].isdigit():
                km = km[2:]  # Enlève "20" au début
            elif len(km) == 6:
                km = km[1:]  # Enlève le premier chiffre
        # Met en forme avec des espaces
        try:
            km_int = int(km)
            if km_int > 1000000:  # Trop grand, probablement une erreur
                km_int = km_int // 100
            return f"{km_int:,}".replace(",", " ")
        except:
            return km
    return None

def extract_car_details(text):
    """Extrait les détails de la voiture (km, carburant, etc.)"""
    details = []
    
    # Kilométrage
    km = clean_km_value(text)
    if km:
        details.append(f"{km} km")
    
    # Carburant
    fuels = ['diesel', 'essence', 'électrique', 'hybride', 'gpl']
    for fuel in fuels:
        if fuel in text.lower():
            details.append(fuel.title())
            break
    
    # Transmission
    if 'automatique' in text.lower() or 'auto' in text.lower():
        details.append('Automatique')
    elif 'manuelle' in text.lower() or 'manuel' in text.lower():
        details.append('Manuelle')
    
    # Année (si présente dans les détails)
    year_match = re.search(r'(19[8-9][0-9]|20[0-2][0-9])', text)
    if year_match and not any('km' in d for d in details):
        details.append(year_match.group(0))
    
    return ' | '.join(details) if details else ""

def format_price(price_str):
    """Formate le prix correctement"""
    # Nettoie le texte du prix
    digits = "".join([c for c in price_str if c.isdigit()])
    
    if not digits:
        return "Prix non disponible"
    
    # Corrige les prix avec des chiffres parasites
    if len(digits) > 5 and digits.endswith(('1', '2', '3', '4', '5', '6', '7', '8', '9')):
        if digits[:-1].endswith('00'):
            digits = digits[:-1]
    
    try:
        price_int = int(digits)
        # Vérifie que le prix est plausible (entre 1000 et 40000)
        if 1000 <= price_int <= 40000:
            return f"{price_int:,}".replace(",", " ")
        else:
            return None
    except:
        return None

def extract_year_from_text(text):
    """Extrait l'année du texte"""
    # Cherche les années 1980-2029
    match = re.search(r"(19[8-9][0-9]|20[0-2][0-9])", text)
    return match.group(0) if match else None

def send_telegram_message(cars_data, page_number):
    """Envoie les données à Telegram"""
    if not cars_data:
        print(f"⚠️ Page {page_number}: Aucune donnée à envoyer")
        return False
    
    date_str = datetime.datetime.now().strftime("%H:%M")
    msg = f"✨ *SÉLECTION AVITO (<40k) - PAGE {page_number}/{MAX_PAGES}* ✨\n"
    msg += f"🕒 {date_str}\n"
    msg += "=" * 30 + "\n\n"
    
    car_count = 0
    for car in cars_data[:12]:  # Max 12 annonces par message
        msg += f"🚘 *{car['name']}*\n"
        msg += f"💰 *PRIX :* {car['price']} DH\n"
        msg += f"📍 *VILLE :* {car['ville']}\n"
        msg += f"📅 *MODÈLE :* {car['annee']}\n"
        if car['details']:
            msg += f"⚙️ *INFOS :* {car['details']}\n"
        msg += f"🔗 [Ouvrir l'annonce]({car['url']})\n"
        msg += "─" * 25 + "\n"
        car_count += 1
    
    # Vérification de la longueur du message
    if len(msg) > 4096:  # Limite de Telegram
        print(f"⚠️ Message trop long ({len(msg)} caractères), envoi tronqué")
        msg = msg[:4000] + "\n\n... (message tronqué)"
    
    # Envoi du message
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    
    try:
        print(f"📤 Envoi à Telegram - Page {page_number} ({car_count} annonces)...")
        response = requests.post(
            url, 
            data={
                "chat_id": TELEGRAM_CHAT_ID, 
                "text": msg, 
                "parse_mode": "Markdown", 
                "disable_web_page_preview": True
            },
            timeout=10
        )
        
        # Vérification de la réponse
        if response.status_code == 200:
            response_data = response.json()
            if response_data.get('ok'):
                print(f"✅ Message page {page_number} envoyé avec succès!")
                return True
            else:
                print(f"❌ Erreur Telegram: {response_data.get('description', 'Erreur inconnue')}")
                return False
        else:
            print(f"❌ Erreur HTTP {response.status_code}: {response.text[:200]}")
            return False
            
    except requests.exceptions.Timeout:
        print(f"❌ Timeout lors de l'envoi à Telegram (page {page_number})")
        return False
    except Exception as e:
        print(f"❌ Exception lors de l'envoi: {str(e)}")
        return False

async def scrape_page(page, page_number):
    """Scrape une page spécifique"""
    if page_number == 1:
        url = BASE_URL
    else:
        # Construit l'URL avec le paramètre de pagination
        if '?' in BASE_URL:
            base, params = BASE_URL.split('?', 1)
            url = f"{base}?o={page_number}&{params}"
        else:
            url = f"{BASE_URL}?o={page_number}"
    
    print(f"\n📄 Page {page_number}/{MAX_PAGES}")
    print(f"🌐 URL: {url}")
    
    try:
        await page.goto(url, wait_until="networkidle", timeout=60000)
        
        # Scroll progressif pour charger tout le contenu
        for _ in range(8):
            await page.mouse.wheel(0, 1000)
            await asyncio.sleep(0.5)
        
        # Attend que les annonces chargent
        await asyncio.sleep(2)
        
        content = await page.content()
        soup = BeautifulSoup(content, 'html.parser')
        
        # Trouve tous les liens d'annonces
        annonces = soup.find_all('a', href=True)
        avito_links = [a for a in annonces if '/vi/' in a.get('href', '')]
        
        print(f"🔗 {len(avito_links)} annonces trouvées sur la page")
        
        page_data = []
        
        for ad in avito_links[:20]:  # Limite à 20 par page
            href = ad.get('href', '')
            full_url = href if href.startswith('http') else f"https://www.avito.ma{href}"
            
            # Récupère tout le texte de l'annonce
            ad_text = ad.get_text(strip=True)
            all_text = ' '.join([elem.get_text(strip=True) for elem in ad.find_all(['h3', 'p', 'span', 'div'])])
            combined_text = ad_text + ' ' + all_text
            
            # Extraction du prix
            price_match = re.search(r'(\d[\d\s]*)\s*DH', combined_text)
            if not price_match:
                price_match = re.search(r'(\d[\d\s]*)\s*MAD', combined_text)
            
            if not price_match:
                continue
                
            raw_price = price_match.group(1) + " DH"
            price = format_price(raw_price)
            
            if not price:  # Prix invalide ou hors fourchette
                continue
            
            # Extraction du nom
            name = extract_car_name(combined_text)
            if name == "Voiture" or len(name) < 2:
                continue
            
            # Extraction de la ville
            ville = "Maroc"
            cities = [
                'Casablanca', 'Rabat', 'Marrakech', 'Fès', 'Tanger', 'Agadir',
                'Meknès', 'Oujda', 'Kénitra', 'Tétouan', 'Salé', 'Nador',
                'Settat', 'El Jadida', 'Taza', 'Khouribga', 'Beni Mellal',
                'Safi', 'Berrechid', 'Témara', 'Guelmim', 'Laayoune'
            ]
            for city in cities:
                if city.lower() in combined_text.lower():
                    ville = city
                    break
            
            # Extraction de l'année
            annee = extract_year_from_text(combined_text)
            if not annee:
                annee = extract_year_from_text(name) or "N/C"
            
            # Extraction des détails
            details = extract_car_details(combined_text)
            
            # Évite les doublons par URL
            if not any(car['url'] == full_url for car in page_data):
                page_data.append({
                    "name": name[:40],
                    "price": price,
                    "ville": ville,
                    "annee": annee,
                    "details": details,
                    "url": full_url
                })
        
        return page_data
        
    except Exception as e:
        print(f"❌ Erreur lors du scraping de la page {page_number}: {str(e)}")
        return []

async def scrape_avito():
    """Fonction principale de scraping"""
    print("🚀 Démarrage du scraper Avito...")
    print("=" * 50)
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=['--disable-blink-features=AutomationControlled']
        )
        
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={'width': 1920, 'height': 1080}
        )
        
        total_annonces = 0
        
        try:
            for i in range(1, MAX_PAGES + 1):
                page = await context.new_page()
                try:
                    cars_data = await scrape_page(page, i)
                    
                    if cars_data:
                        # Enlève les doublons par URL
                        unique_cars = []
                        seen_urls = set()
                        for car in cars_data:
                            if car['url'] not in seen_urls:
                                seen_urls.add(car['url'])
                                unique_cars.append(car)
                        
                        if unique_cars:
                            success = send_telegram_message(unique_cars, i)
                            if success:
                                total_annonces += len(unique_cars)
                                print(f"✅ Page {i}: {len(unique_cars)} annonces envoyées")
                            else:
                                print(f"❌ Page {i}: Échec de l'envoi")
                        else:
                            print(f"⚠️ Page {i}: Aucune annonce unique trouvée")
                    else:
                        print(f"⚠️ Page {i}: Aucune annonce trouvée")
                        
                except Exception as e:
                    print(f"❌ Erreur page {i}: {str(e)}")
                finally:
                    await page.close()
                
                # Pause entre les pages pour éviter le blocage
                await asyncio.sleep(3)
                
        finally:
            await browser.close()
        
        print("\n" + "=" * 50)
        print(f"🎉 Scraping terminé!")
        print(f"📊 Total des annonces envoyées: {total_annonces}")
        print("=" * 50)

if __name__ == "__main__":
    print("=" * 50)
    print("🚗 SCRIPT DE SCRAPING AVITO - VOITURES < 40 000 DH")
    print("=" * 50)
    asyncio.run(scrape_avito())
