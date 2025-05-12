import random

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright


def get_login(filename: str) -> tuple:
    username = ''
    password = ''
    with open(filename, 'r', encoding='utf-8') as file:
        for line in file.readlines():
            if line.lower().startswith("username:"):
                username = line.split()[1]
            elif line.lower().startswith('password:'):
                password = line.split()[1]
            if username and password:
                break
    return username, password


def wait(page, millis: int, variance: int = 100):
    page.wait_for_timeout(millis + random.randint(-variance, variance))


def main():

    with sync_playwright() as p:
        browser = p.webkit.launch(headless=False, slow_mo=50)
        page = browser.new_page()
        page.goto("https://www.instagram.com/")
        print("Loaded page:", page.title())

        # Log in
        # page.get_by_role("button", name="Log in").click()
        username, password = get_login('scrapers/instagram/login.txt')
        page.get_by_role("textbox", name="username").fill(username)
        page.get_by_role("textbox", name="password").fill(password)
        wait(page, 500)
        page.get_by_role("button").filter(has_not_text="Facebook").filter(has_text="Log in").click()
        page.get_by_role("button").filter(has_text="Not now").click()
        print("Logged in")

        urls = []
        # accounts = 'venen_0', '999_adj', #'quedup_toronto', 'venusinfoil', 'format.toronto', 'bsmt254toronto'
        accounts = '999_adj',
        # Visit accounts
        for account in accounts:
            print(f"Visiting account: {account}")
            page.goto(f"https://www.instagram.com/stories/{account}/")

            # Check out stories
            # page.get_by_role("button").get_by_alt_text(f"{account}'s profile picture").click()
            wait(page, 3100, 200)
            breakpoint()

            i = 0
            while(True):
                # Save HTML for reference
                filename = f"html/{account}_story_{i}.html"
                with open(filename, 'w', encoding='utf-8') as file:
                    html_content = page.content()
                    file.write(html_content)
                    print(f"Wrote to {filename}")

                # Parse HTML
                soup = BeautifulSoup(html_content, 'html.parser')
                buttons = soup.find_all('button')
                for button in buttons:
                    if button.get_text().startswith('Link icon'):
                        url = button.get_text()[len('Link icon'):]
                        url = url.split()[0]
                        urls.append(url)
                if urls:
                    print("Found links:", urls)

                # TODO Continue if there are more stories
                page.get_by_role('button', name='Next').click()
                wait(page, 500)
                if not sth:
                    break

        browser.close()


if __name__ == "__main__":
    main()
