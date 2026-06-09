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

# VÉRIFICATION CRITIQUE : Variables d'environnement
print(f"🔍 Vérification des configurations:")
print(f"TELEGRAM_TOKEN: {'✅ Présent' if TELEGRAM_TOKEN else '❌ MANQUANT'}")
print(f"TELEGRAM_CHAT_ID: {'✅ Présent' if TELEGRAM_CHAT_ID else '❌ MANQUANT'}")
print(f"BASE_URL: {BASE_URL}")
print("-" * 50)

if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
    print("❌ ERREUR: Variables d'environnement Telegram manquantes!")
    print("   Vérifiez votre fichier .env")
    exit(1)

def send_telegram_message_sync(data, page_number):
    """Version synchrone de l'envoi Telegram (pour être appelée dans async)"""
    if not data:
        print(f"⚠️ Page {page_number}: Aucune donnée à envoyer")
        return False
    
    date_str = datetime.datetime.now().strftime("%H:%M")
    msg = f"✨ *SÉLECTION AVITO (<40k) - PAGE {page_number}/{MAX_PAGES}* ✨\n"
    msg += f"🕒 {date_str}\n"
    msg += "=" * 25 + "\n\n"
    
    car_count = 0
    for car in data[:10]:
        msg += f"🚘 *NOM :* {car['name']}\n"
        msg += f"💰 *PRIX :* {car['price']} DH\n"
        msg += f"📍 *VILLE :* {car['ville']}\n"
        msg += f"📅 *MODÈLE :* {car['annee']}\n"
        if car['details']:
            msg += f"⚙️ *INFOS :* {car['details']}\n"
        msg += f"🔗 [Ouvrir l'annonce]({car['url']})\n"
        msg += "─" * 15 + "\n"
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
            print(f"❌ Erreur HTTP {response.status_code}: {response.text}")
            return False
            
    except requests.exceptions.Timeout:
        print(f"❌ Timeout lors de l'envoi à Telegram (page {page_number})")
        return False
    except Exception as e:
        print(f"❌ Exception lors de l'envoi: {str(e)}")
        return False

def format_price(price_str):
    print(f"💰 Formatage du prix: {price_str}")  # Debug
    # 1. On garde uniquement les chiffres
    digits = "".join([c for c in price_str if c.isdigit()])
    
    # 2. LOGIQUE DE CORRECTION :
    # Si le prix semble avoir un chiffre de trop (ex: 580001 pour 58000)
    # On sait que les prix ronds finissent souvent par 000 au Maroc.
    # Si le prix dépasse 5 chiffres et finit par un chiffre parasite du crédit
    if len(digits) > 5 and digits.endswith(('1', '2', '3', '4', '5', '6', '7', '8', '9')):
        # On vérifie si enlever le dernier chiffre rend le prix plus "normal" (multiple de 100 ou 1000)
        if digits[:-1].endswith('00'):
            digits = digits[:-1]
            
    try:
        formatted = f"{int(digits):,}".replace(",", " ")
        print(f"   → Prix formaté: {formatted}")
        return formatted
    except:
        print(f"   → Échec formatage, retour: {digits}")
        return digits

def extract_year_from_text(text):
    match = re.search(r"(19|20)\d{2}", text)
    return match.group(0) if match else None

async def scrape_avito():
    print("🚀 Démarrage du scraping...")
    
    async with async_playwright() as p:
        print("📱 Lancement du navigateur...")
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
        
        total_annonces = 0
        
        for i in range(1, MAX_PAGES + 1):
            if i == 1:
                url = BASE_URL
            else:
                url = BASE_URL.replace("?", f"?o={i}&")
            
            print(f"\n📄 Page {i}/{MAX_PAGES} - URL: {url}")
            
            page = await context.new_page()
            page_data = []

            try:
                print(f"⏳ Chargement de la page {i}...")
                await page.goto(url, wait_until="load", timeout=60000)
                
                print(f"📜 Scroll sur la page {i}...")
                for _ in range(6):
                    await page.mouse.wheel(0, 800)
                    await asyncio.sleep(1)
                
                print(f"🔍 Extraction du contenu HTML...")
                content = await page.content()
                soup = BeautifulSoup(content, 'html.parser')
                
                # Debug: Afficher le titre de la page
                title = soup.find('title')
                if title:
                    print(f"📌 Titre de la page: {title.get_text()[:100]}")
                
                # Méthode alternative pour trouver les annonces
                annonces = soup.find_all('a', href=True)
                print(f"🔗 Nombre total de liens trouvés: {len(annonces)}")
                
                avito_links = [a for a in annonces if "/vi/" in a.get('href', '') or ".htm" in a.get('href', '')]
                print(f"🚗 Liens Avito trouvés: {len(avito_links)}")
                
                for idx, ad in enumerate(avito_links[:20]):  # Limiter pour le debug
                    href = ad.get('href', '')
                    full_url = href if href.startswith("http") else "https://www.avito.ma" + href
                    
                    # Debug: Afficher le texte de l'annonce
                    ad_text = ad.get_text(strip=True)
                    print(f"\n🔍 Annonce {idx+1}:")
                    print(f"   Texte: {ad_text[:100]}...")
                    
                    # Chercher le prix avec une méthode plus simple
                    price_match = re.search(r'(\d[\d\s]*)\s*DH', ad_text)
                    if not price_match:
                        price_match = re.search(r'(\d[\d\s]*)\s*MAD', ad_text)
                    
                    if price_match:
                        raw_price = price_match.group(1) + " DH"
                        print(f"   Prix trouvé: {raw_price}")
                        price = format_price(raw_price)
                        
                        # Extraire le nom (première ligne ou premier élément)
                        name_parts = ad_text.split('\n')
                        name = name_parts[0] if name_parts else "Voiture"
                        if len(name) > 50:
                            name = name[:50]
                        
                        # Extraire la ville (chercher dans le texte)
                        ville = "Maroc"
                        city_match = re.search(r'(Casablanca|Rabat|Marrakech|Fès|Tanger|Agadir|Meknès|Oujda|Kénitra|Tétouan|Salé|Nador|Settat|El Jadida|Taza|Khouribga|Beni Mellal|Safi|Berrechid|Témara)', ad_text, re.IGNORECASE)
                        if city_match:
                            ville = city_match.group(1)
                        
                        # Extraire l'année
                        annee = extract_year_from_text(ad_text) or "N/C"
                        
                        # Extraire les détails
                        details_parts = []
                        km_match = re.search(r'(\d[\d\s]*)\s*kms?', ad_text, re.IGNORECASE)
                        if km_match:
                            details_parts.append(f"{km_match.group(1)} km")
                        
                        fuel_match = re.search(r'(Diesel|Essence|Électrique|Hybride)', ad_text, re.IGNORECASE)
                        if fuel_match:
                            details_parts.append(fuel_match.group(1))
                        
                        details = " | ".join(details_parts)
                        
                        car_data = {
                            "name": name[:30],
                            "price": price,
                            "ville": ville,
                            "annee": annee,
                            "details": details,
                            "url": full_url
                        }
                        
                        print(f"   ✅ Annonce extraite: {car_data['name']} - {car_data['price']}")
                        page_data.append(car_data)
                    else:
                        print(f"   ❌ Aucun prix trouvé")
                
                if page_data:
                    # Enlever les doublons
                    unique = list({v['url']:v for v in page_data}.values())
                    print(f"\n📊 Page {i}: {len(unique)} annonces uniques trouvées")
                    
                    # Envoyer à Telegram
                    print(f"📨 Envoi à Telegram...")
                    success = send_telegram_message_sync(unique, i)
                    if success:
                        total_annonces += len(unique)
                        print(f"✅ Page {i} envoyée avec succès!")
                    else:
                        print(f"❌ Échec de l'envoi pour la page {i}")
                else:
                    print(f"⚠️ Page {i}: Aucune annonce valide trouvée")

            except Exception as e:
                print(f"❌ Erreur détaillée page {i}: {type(e).__name__}: {str(e)}")
                import traceback
                traceback.print_exc()
            finally:
                await page.close()
            await asyncio.sleep(2)
        
        await browser.close()
        print(f"\n🎉 Scraping terminé! Total annonces envoyées: {total_annonces}")

if __name__ == "__main__":
    print("=" * 50)
    print("🚗 SCRIPT DE SCRAPING AVITO AVEC CORRECTIONS")
    print("=" * 50)
    asyncio.run(scrape_avito())
