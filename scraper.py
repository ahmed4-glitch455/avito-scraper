import asyncio
import os
import requests
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_API = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
URL_EXEMPLE = "https://www.avito.ma/fr/bourgogne/voitures_d_occasion/Mercedes_classe_E_220_56088631.htm"

async def scrape_details_voiture(url):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        # On simule un écran large pour forcer l'affichage des infos
        context = await browser.new_context(viewport={'width': 1920, 'height': 1080})
        page = await context.new_page()

        try:
            print(f"Analyse en cours...")
            await page.goto(url, wait_until="networkidle", timeout=60000)
            
            # On attend 5 secondes pour être SÛR que le prix et les détails sont affichés
            await asyncio.sleep(5)
            
            content = await page.content()
            soup = BeautifulSoup(content, 'html.parser')

            # 1. Extraction du Titre
            titre = soup.find('h1').get_text(strip=True) if soup.find('h1') else "Sans titre"

            # 2. Extraction du Prix (Recherche par texte contenant "DH")
            prix = "Prix non affiché"
            # On cherche tous les éléments qui pourraient contenir le prix
            for p_tag in soup.find_all(['p', 'h2', 'span']):
                txt = p_tag.get_text(strip=True)
                if "DH" in txt and any(char.isdigit() for char in txt):
                    prix = txt
                    break

            # 3. Extraction des détails (Année, KM, Ville)
            # On cherche dans toute la page les textes qui contiennent nos mots-clés
            infos = {"Ville": "N/C", "Année": "N/C", "KM": "N/C"}
            
            for span in soup.find_all(['span', 'p', 'li']):
                text = span.get_text(strip=True)
                if "Année-Modèle" in text:
                    # On essaie de prendre le texte juste après ou à l'intérieur
                    infos["Année"] = text.replace("Année-Modèle", "").strip()
                elif "Kilométrage" in text:
                    infos["KM"] = text.replace("Kilométrage", "").strip()
                elif "Secteur" in text:
                    infos["Ville"] = text.replace("Secteur", "").strip()

            return {
                "titre": titre,
                "prix": prix,
                "ville": infos["Ville"],
                "annee": infos["Année"],
                "km": infos["KM"]
            }

        except Exception as e:
            print(f"Erreur : {e}")
            return None
        finally:
            await browser.close()

def envoyer_telegram(data):
    msg = (f"✨ *Analyse Réussie !*\n\n"
           f"🚘 *Modèle :* {data['titre']}\n"
           f"💰 *Prix :* {data['prix']}\n"
           f"📍 *Ville :* {data['ville']}\n"
           f"📅 *Année :* {data['annee']}\n"
           f"🛣️ *KM :* {data['km']}\n\n"
           f"[Ouvrir l'annonce]({URL_EXEMPLE})")

    url = f"https://api.telegram.org/bot{TELEGRAM_API}/sendMessage"
    requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "Markdown"})

async def main():
    resultat = await scrape_details_voiture(URL_EXEMPLE)
    if resultat:
        envoyer_telegram(resultat)

if __name__ == "__main__":
    asyncio.run(main())
