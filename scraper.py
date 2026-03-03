import asyncio
import os
import requests
import sys
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

# --- CONFIGURATION ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_API")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
URL_EXEMPLE = "https://www.avito.ma/fr/bourgogne/voitures_d_occasion/Mercedes_classe_E_220_56088631.htm"

def envoyer_telegram(data):
    """Envoi avec vérification d'erreur explicite."""
    print("Tentative d'envoi vers Telegram...")
    msg = (f"🚀 *Test Réussi !*\n\n"
           f"🚘 *Modèle :* {data['titre']}\n"
           f"💰 *Prix :* {data['prix']}\n"
           f"📍 *Ville :* {data['ville']}\n\n"
           f"[Lien]({URL_EXEMPLE})")

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        res = requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "Markdown"}, timeout=15)
        if res.status_code == 200:
            print("✅ Message envoyé avec succès !")
        else:
            print(f"❌ Erreur Telegram ({res.status_code}): {res.text}")
    except Exception as e:
        print(f"❌ Erreur réseau lors de l'envoi : {e}")

async def scrape():
    async with async_playwright() as p:
        print("Lancement du navigateur...")
        # Lancement avec des options pour passer sous les radars
        browser = await p.chromium.launch(headless=True)
        
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={'width': 1280, 'height': 800}
        )
        
        page = await context.new_page()
        
        try:
            print(f"Navigation vers : {URL_EXEMPLE}")
            # On utilise 'load' au lieu de 'networkidle' pour éviter d'attendre indéfiniment
            await page.goto(URL_EXEMPLE, wait_until="load", timeout=60000)
            
            print("Page chargée. Attente de 5s pour le contenu dynamique...")
            await asyncio.sleep(5)
            
            # Prendre une capture d'écran (pour déboguer si besoin dans les logs GitHub)
            # await page.screenshot(path="debug.png") 

            content = await page.content()
            soup = BeautifulSoup(content, 'html.parser')

            # Extraction simplifiée
            titre = soup.find('h1').get_text(strip=True) if soup.find('h1') else "Titre introuvable"
            print(f"Titre trouvé : {titre}")

            prix = "N/A"
            for tag in soup.find_all(['p', 'h2', 'span', 'div']):
                txt = tag.get_text(strip=True)
                if "DH" in txt and any(c.isdigit() for c in txt) and len(txt) < 20:
                    prix = txt
                    break
            
            ville = "N/A"
            for span in soup.find_all('span'):
                if "Secteur" in span.get_text():
                    ville = span.get_text().replace("Secteur", "").strip()

            data = {"titre": titre, "prix": prix, "ville": ville}
            envoyer_telegram(data)

        except Exception as e:
            print(f"💥 ERREUR pendant le scraping : {e}")
        finally:
            await browser.close()
            print("Navigateur fermé.")

if __name__ == "__main__":
    if not TELEGRAM_API or not TELEGRAM_CHAT_ID:
        print("❌ ERREUR : Les variables TELEGRAM_TOKEN ou TELEGRAM_CHAT_ID sont vides !")
        sys.exit(1)
    asyncio.run(scrape())
