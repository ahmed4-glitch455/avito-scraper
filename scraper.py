import asyncio
import os
import requests
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

# --- CONFIGURATION ---
TELEGRAM_API = os.getenv("TELEGRAM_API")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
# Votre lien exemple
URL_EXEMPLE = "https://www.avito.ma/fr/bourgogne/voitures_d_occasion/Mercedes_classe_E_220_56088631.htm"

async def scrape_details_voiture(url):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        try:
            print(f"Analyse de l'annonce : {url}")
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            # On laisse 3 secondes pour que le JavaScript affiche le prix
            await asyncio.sleep(3)
            
            content = await page.content()
            soup = BeautifulSoup(content, 'html.parser')

            # 1. Extraction du Titre
            titre = soup.find('h1').get_text(strip=True) if soup.find('h1') else "Sans titre"

            # 2. Extraction du Prix (Balise spécifique sur la page détail)
            # Souvent un <p> ou <span> avec une classe contenant 'price'
            prix_tag = soup.find(lambda tag: tag.name in ['p', 'span', 'h2'] and 'price' in str(tag.get('class', [])).lower())
            prix = prix_tag.get_text(strip=True) if prix_tag else "Prix non affiché"

            # 3. Extraction des caractéristiques (Année, Kilométrage, etc.)
            # Avito utilise souvent une liste d'ol/ul ou des div pour les caractéristiques
            infos = {}
            caracs = soup.find_all('div', class_=lambda x: x and 'sc-1g3sn3w' in x) # Classe typique des infos
            
            for item in soup.find_all('li'): # On cherche dans les listes de la page
                text = item.get_text(strip=True)
                if "Année" in text: infos['Année'] = text.replace("Année-Modèle", "").strip()
                if "Kilométrage" in text: infos['KM'] = text.replace("Kilométrage", "").strip()
                if "Secteur" in text: infos['Ville'] = text.replace("Secteur", "").strip()

            return {
                "titre": titre,
                "prix": prix,
                "ville": infos.get('Ville', 'N/C'),
                "annee": infos.get('Année', 'N/C'),
                "km": infos.get('KM', 'N/C')
            }

        except Exception as e:
            print(f"Erreur : {e}")
            return None
        finally:
            await browser.close()

def envoyer_telegram(data):
    if not data: return
    
    msg = f"✨ *Nouvelle Opportunité trouvée !*\n\n"
    msg += f"🚘 *Modèle :* {data['titre']}\n"
    msg += f"💰 *Prix :* {data['prix']}\n"
    msg += f"📍 *Ville :* {data['ville']}\n"
    msg += f"📅 *Année :* {data['annee']}\n"
    msg += f"🛣️ *KM :* {data['km']}\n\n"
    msg += f"[Voir l'annonce sur Avito]({URL_EXEMPLE})"

    url = f"https://api.telegram.org/bot{TELEGRAM_API}/sendMessage"
    requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "Markdown"})

async def main():
    resultat = await scrape_details_voiture(URL_EXEMPLE)
    if resultat:
        envoyer_telegram(resultat)
        print("Détails envoyés sur Telegram !")

if __name__ == "__main__":
    asyncio.run(main())
