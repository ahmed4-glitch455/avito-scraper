import asyncio
import os
import datetime
import requests
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_API")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
BASE_URL = "https://www.avito.ma/fr/maroc/voitures_d_occasion-%C3%A0_vendre"
MAX_PAGES = 30 

def send_telegram_page(data, page_number):
    if not data: return
    date_str = datetime.datetime.now().strftime("%H:%M")
    header = f"🚗 *Avito Page {page_number}/{MAX_PAGES}* ({date_str})\n"
    header += "```\n"
    header += f"{'Modèle':<18} | {'Prix':<10}\n"
    header += "-" * 31 + "\n"
    body = "".join([f"{car['name']:<18} | {car['price']:<10}\n" for car in data[:15]])
    msg = header + body + "```"
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "Markdown"}, timeout=10)
    except:
        print("Erreur d'envoi Telegram")

async def scrape_avito():
    async with async_playwright() as p:
        # Lancement du navigateur
        browser = await p.chromium.launch(headless=True)
        # Utilisation d'un seul contexte pour toute la session (plus stable pour la navigation)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )

        for i in range(1, MAX_PAGES + 1):
            url = BASE_URL if i == 1 else f"{BASE_URL}?o={i}"
            
            # Création d'une nouvelle page à chaque itération
            page = await context.new_page()
            page_data = []

            try:
                print(f"Analyse Page {i} : {url}")
                # Changement : wait_until="load" est souvent plus fiable que networkidle sur Avito
                await page.goto(url, wait_until="load", timeout=60000)
                
                # Scroll progressif pour simuler un humain et charger le Lazy Loading
                for _ in range(3):
                    await page.mouse.wheel(0, 1000)
                    await asyncio.sleep(1)

                content = await page.content()
                soup = BeautifulSoup(content, 'html.parser')
                
                # Recherche des annonces (on cible les liens 'a' qui sont les conteneurs réels)
                annonces = soup.find_all('a', href=True)

                for ad in annonces:
                    # Sélecteurs basés sur vos classes iHApav / dJAfqm
                    title_tag = ad.find(['h3', 'p', 'span'], class_='iHApav')
                    price_tag = ad.find(['p', 'span'], class_=['dJAfqm', 'hsBiLW'])

                    if title_tag and price_tag:
                        titre = title_tag.get_text(strip=True)[:18]
                        prix = price_tag.get_text(strip=True).replace("DH", "").replace(" ", "").strip()
                        
                        if any(char.isdigit() for char in prix):
                            page_data.append({"name": titre, "price": prix})

                # Nettoyage des doublons
                final_data = []
                seen = set()
                for car in page_data:
                    if car['name'] not in seen:
                        final_data.append(car)
                        seen.add(car['name'])

                if final_data:
                    send_telegram_page(final_data, i)
                    print(f"✅ Page {i} : {len(final_data)} voitures envoyées.")
                else:
                    print(f"⚠️ Page {i} : Aucune donnée extraite.")

            except Exception as e:
                print(f"❌ Erreur Page {i}: {e}")
            
            finally:
                # Fermeture impérative de l'onglet pour libérer la mémoire
                await page.close()
            
            # Pause plus longue entre les pages pour éviter le blocage IP par Avito
            await asyncio.sleep(5)

        await browser.close()

if __name__ == "__main__":
    asyncio.run(scrape_avito())
