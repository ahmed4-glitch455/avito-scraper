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
BASE_URL = "https://www.avito.ma/fr/maroc/voitures_d_occasion-%C3%A0_vendre?price=-60000"
MAX_PAGES = 30 

def send_telegram_page(data, page_number):
    if not data: return
    date_str = datetime.datetime.now().strftime("%H:%M")
    header = f"🚗 *Avito Page {page_number}/30* ({date_str})\n"
    header += "```\n"
    header += f"{'Modèle':<18} | {'Prix':<10}\n"
    header += "-" * 31 + "\n"
    body = "".join([f"{car['name']:<18} | {car['price']:<10}\n" for car in data])
    msg = header + body + "```"
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "Markdown"})

async def scrape_avito():
    async with async_playwright() as p:
        # Lancement avec des paramètres pour masquer le mode automatique
        browser = await p.chromium.launch(headless=True, args=[
            '--disable-blink-features=AutomationControlled',
            '--no-sandbox'
        ])
        
        # Simulation d'un navigateur Chrome très standard
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={'width': 1280, 'height': 900}
        )

        for i in range(1, MAX_PAGES + 1):
            url = f"{BASE_URL}&o={i}"
            page = await context.new_page()
            page_data = []

            try:
                print(f"Analyse Page {i}...")
                # On va directement à l'URL
                await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                
                # CRUCIAL : On attend que le texte "DH" apparaisse sur la page (signe que les prix sont chargés)
                try:
                    await page.wait_for_selector("text=DH", timeout=20000)
                    print(f"Contenu détecté sur la page {i}")
                except:
                    print(f"⚠️ Aucun prix détecté sur la page {i}, tentative de scroll...")
                    await page.mouse.wheel(0, 1000) # On scrolle vers le bas pour déclencher le chargement
                    await asyncio.sleep(3)

                content = await page.content()
                soup = BeautifulSoup(content, 'html.parser')
                
                # Méthode d'extraction ultra-flexible
                # On cherche tous les blocs qui contiennent un prix (DH)
                annonces = soup.find_all('div', class_=lambda x: x and ('card' in x.lower() or 'item' in x.lower()))
                
                # Si la recherche par div échoue, on prend les p directement
                if not annonces or len(annonces) < 5:
                    # On cherche les conteneurs parents des prix
                    prix_tags = soup.find_all(lambda tag: tag.name == 'p' and 'DH' in tag.text)
                    for p_tag in prix_tags:
                        parent = p_tag.find_parent('div')
                        if parent and parent not in annonces:
                            annonces.append(parent)

                for ad in annonces:
                    try:
                        # On cherche le prix
                        p_price = ad.find(lambda t: t.name == 'p' and 'DH' in t.text)
                        # On cherche le titre (souvent un h2 ou un p avec une classe spécifique)
                        p_title = ad.find(['h2', 'h3', 'p'])
                        
                        if p_price and p_title:
                            price_text = p_price.get_text(strip=True).replace(" DH", "").replace(" ", "")
                            title_text = p_title.get_text(strip=True)[:18]
                            
                            # On vérifie que c'est bien un prix numérique
                            if any(char.isdigit() for char in price_text):
                                page_data.append({"name": title_text, "price": price_text})
                    except:
                        continue

                # Suppression des doublons potentiels
                unique_data = [dict(t) for t in {tuple(d.items()) for d in page_data}]

                if unique_data:
                    send_telegram_page(unique_data[:20], i) # On envoie les 20 premières
                    print(f"✅ Page {i} : {len(unique_data)} voitures trouvées.")
                else:
                    print(f"❌ Page {i} toujours vide.")

            except Exception as e:
                print(f"Erreur Page {i}: {e}")
            
            finally:
                await page.close()

            await asyncio.sleep(4) # Pause plus longue pour ne pas paraître suspect

        await browser.close()

if __name__ == "__main__":
    asyncio.run(scrape_avito())
