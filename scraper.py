import asyncio
import os
import requests
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

# --- ICI ON ADAPTE LE NOM ---
# Le code va maintenant chercher "TELEGRAM_API" dans vos secrets GitHub
TELEGRAM_TOKEN = os.getenv("TELEGRAM_API") 
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

URL_EXEMPLE = "https://www.avito.ma/fr/bourgogne/voitures_d_occasion/Mercedes_classe_E_220_56088631.htm"

async def test_connexion():
    print(f"Démarrage du test...")
    print(f"Vérification du Token : {'Configuré' if TELEGRAM_TOKEN else 'VIDE (Erreur de nom ?)'}")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        try:
            await page.goto(URL_EXEMPLE, wait_until="domcontentloaded")
            await asyncio.sleep(4)
            
            content = await page.content()
            soup = BeautifulSoup(content, 'html.parser')
            titre = soup.find('h1').get_text(strip=True) if soup.find('h1') else "Mercedes"

            # Préparation du message
            msg = f"✅ *Test de connexion réussi !*\n\nLe robot a bien trouvé : {titre}"
            
            # Envoi à Telegram
            url_tele = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
            res = requests.post(url_tele, data={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "Markdown"})
            
            if res.status_code == 200:
                print("Succès : Message reçu sur Telegram !")
            else:
                print(f"Erreur Telegram : {res.text}")

        except Exception as e:
            print(f"Erreur technique : {e}")
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(test_connexion())
