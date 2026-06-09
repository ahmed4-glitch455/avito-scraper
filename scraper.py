import asyncio
import os
import datetime
import re
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
import httpx
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

# --- CONFIGURATION ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_API")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
# L'URL combine maintenant le filtre de la marque (Palio/Siena) et le prix max de 40 000 DH
BASE_URL = "https://www.avito.ma/fr/maroc/voitures_d_occasion-%C3%A0_vendre?brand=17&model=palio,siena&brand_model=17_palio,17_siena&price=-40000"
MAX_PAGES = 30 

def format_price(price_str):
    # 1. On garde uniquement les chiffres
    digits = "".join([c for c in price_str if c.isdigit()])
    
    # 2. LOGIQUE DE CORRECTION DU CRÉDIT PARASITE :
    # Si le prix dépasse 5 chiffres et finit par un chiffre non nul (parasite de mensualité)
    if len(digits) > 5 and digits.endswith(('1', '2', '3', '4', '5', '6', '7', '8', '9')):
        if digits[:-1].endswith('00'):
            digits = digits[:-1]
            
    try:
        return f"{int(digits):,}".replace(",", " ")
    except ValueError:
        return digits

def extract_year_from_text(text):
    match = re.search(r"(19|20)\d{2}", text)
    return match.group(0) if match else None

def build_page_url(base_url, page_number):
    """Gère proprement la pagination en injectant le paramètre 'o' dans l'URL."""
    if page_number == 1:
        return base_url
    url_parts = list(urlparse(base_url))
    query = parse_qs(url_parts[4])
    query['o'] = [str(page_number)]
    url_parts[4] = urlencode(query, doseq=True)
    return urlunparse(url_parts)

async def send_telegram_page_async(client, data, page_number):
    """Envoie la sélection d'annonces sur Telegram de façon asynchrone."""
    if not data: 
        return
        
    date_str = datetime.datetime.now().strftime("%H:%M")
    msg = f"✨ *SÉLECTION AVITO (<40k) - PAGE {page_number}/{MAX_PAGES}* ✨\n"
    msg += f"🕒 {date_str}\n"
    msg += "=" * 25 + "\n\n"
    
    # On limite à 10 annonces maximum par message pour éviter de dépasser la limite de caractères de Telegram
    for car in data[:10]:
        msg += f"🚘 *NOM :* {car['name']}\n"
        msg += f"💰 *PRIX :* {car['price']} DH\n"
        msg += f"📍 *VILLE :* {car['ville']}\n"
        msg += f"📅 *MODÈLE :* {car['annee']}\n"
        if car['details']:
            msg += f"⚙️ *INFOS :* {car['details']}\n"
        msg += f"🔗 [Ouvrir l'annonce]({car['url']})\n"
        msg += "─" * 15 + "\n"
    
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    
    try:
        response = await client.post(url, data={
            "chat_id": TELEGRAM_CHAT_ID, 
            "text": msg, 
            "parse_mode": "Markdown", 
            "disable_web_page_preview": True
        })
        # Lève une exception claire si l'API Telegram renvoie une erreur (400, 401, etc.)
        response.raise_for_status()
    except Exception as e:
        print(f"❌ Erreur lors de l'envoi Telegram : {e}")

async def scrape_avito():
    # Utilisation d'un client HTTP partagé pour toute la session
    async with httpx.AsyncClient() as client, async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            locale="fr-FR"
        )

        for i in range(1, MAX_PAGES + 1):
            url = build_page_url(BASE_URL, i)
            page = await context.new_page()
            page_data = []

            try:
                print(f"Analyse Page {i} -> {url}")
                await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                
                # Déclenchement du Lazy Loading (un peu plus rapide et plus profond)
                for _ in range(4):
                    await page.mouse.wheel(0, 1200)
                    await asyncio.sleep(0.5)

                content = await page.content()
                soup = BeautifulSoup(content, 'html.parser')
                
                # Ciblage direct des balises de liens des annonces d'Avito
                annonces = soup.find_all('a', class_=re.compile(r'sc-1jge648-0'))

                for ad in annonces:
                    href = ad.get('href', '')
                    if not href:
                        continue
                        
                    full_url = href if href.startswith("http") else "https://www.avito.ma" + href
                    
                    # --- EXTRACTION SÉLECTEURS HTML RELEVÉS ---
                    title_tag = ad.find(['p', 'h3', 'span'], class_=re.compile(r'iHApav'))
                    price_tag = ad.find(['span', 'p'], class_=re.compile(r'(hsBiLW|eCXWei)'))
                    
                    if title_tag:
                        name = title_tag.get_text(strip=True)
                        
                        # Gestion du prix
                        if price_tag:
                            raw_price = price_tag.get_text(strip=True).split('DH')[0] + " DH"
                            price = format_price(raw_price)
                        else:
                            price = "Demander le prix"
                        
                        # Badges (Contient l'Année, le Carburant, la Puissance...)
                        badges = ad.find_all('span', class_=re.compile(r'gbLqLI'))
                        all_texts = [b.get_text(strip=True) for b in badges if b.get_text(strip=True)]
                        
                        # Recherche de la ville via sa classe dédiée
                        ville_tag = ad.find('p', class_=re.compile(r'layWaX'))
                        ville = ville_tag.get_text(strip=True).replace("Voitures d'occasion dans", "").strip() if ville_tag else "Maroc"
                        
                        # Extraction de l'année (méthode de secours basée sur le titre ou via les badges)
                        annee = extract_year_from_text(name) or "N/C"
                        autres = []

                        for text in all_texts:
                            lower_text = text.lower()
                            if "dh" in lower_text or "/mois" in lower_text:
                                continue
                            
                            # Si le texte correspond exactement à une année
                            if re.match(r"^(19|20)\d{2}$", text):
                                annee = text
                            # Si le texte contient des détails techniques
                            elif any(x in lower_text for x in ['km', 'diesel', 'essence', 'manuel', 'auto', 'cv']):
                                if text not in autres: 
                                    autres.append(text)

                        page_data.append({
                            "name": name[:30],
                            "price": price,
                            "ville": ville,
                            "annee": annee,
                            "details": " | ".join(autres),
                            "url": full_url
                        })

                print(f"-> Annonces trouvées et parsées sur la page {i} : {len(page_data)}")

                if page_data:
                    # Suppression des doublons d'URL sur la même page
                    unique = list({v['url']: v for v in page_data}.values())
                    await send_telegram_page_async(client, unique, i)
                    print(f"✅ Page {i} traitée et envoyée avec succès.")
                else:
                    # Si aucune donnée n'est collectée, sauvegarde d'un screenshot pour le débogage (GitHub Actions Artifacts)
                    if i == 1:
                        await page.screenshot(path="screenshot_page_1.png")
                        print("📸 Capture d'écran de la page 1 enregistrée ('screenshot_page_1.png') car aucune donnée n'a été extraite.")

            except Exception as e:
                print(f"❌ Erreur lors du traitement de la Page {i}: {e}")
            finally:
                await page.close()
            
            # Politesse envers le serveur pour éviter les bannissements d'IP trop agressifs
            await asyncio.sleep(1.5)

        await browser.close()

if __name__ == "__main__":
    asyncio.run(scrape_avito())
