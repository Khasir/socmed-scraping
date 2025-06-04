import base64
from collections import defaultdict
import csv
import datetime
import os
import random

from bs4 import BeautifulSoup
from openai import OpenAI
from playwright.sync_api import sync_playwright, expect
from pydantic import BaseModel


def get_login(filename: str) -> tuple:
    """Load login credentials from text file"""
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
    if not username or not password:
        raise ValueError(f"File does not contain login credentials: {filename}")
    return username, password


def wait(page, millis: int, variance: int = 100):
    """Load a page after a given timeout and random variance."""
    if page:
        page.wait_for_timeout(millis + random.randint(-variance, variance))


def encode_image(image_path: str):
    """Return base64 encoding of an image"""
    with open(image_path, 'rb') as file:
        return base64.b64encode(file.read()).decode("utf-8")


def read_file(file_path: str) -> str:
    with open(file_path, 'r', encoding='utf-8') as file:
        return file.read().strip()


class EventDetails(BaseModel):
    event_name: str
    start_date: str
    artist: str
    location: str
    other_notes: str


def parse_image(client: OpenAI, system_prompt: str, user_prompt: str, image_path: str) -> dict:
    response = client.responses.parse(
        model='gpt-4.1-mini',
        input=[
            {
                "role": "system",
                "content": system_prompt
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": user_prompt
                    },
                    {
                        "type": "input_image",
                        "image_url": f"data:image/png;base64,{encode_image(image_path)}"
                    }
                ]
            }
        ],
        text_format=EventDetails
    )
    return response


def main(output_filename: str = 'output.csv'):
    html_dir = "scrapers/instagram/html"
    image_dir = "scrapers/instagram/img"
    user_prompt = read_file("scrapers/instagram/openai/image_parsing_prompt.txt")
    system_prompt = read_file("scrapers/instagram/openai/system_prompt.txt")
    system_prompt = system_prompt.format(datetime.datetime.today().strftime("%c"))  # Add current timestamp
    openai_client = OpenAI(api_key=read_file("scrapers/instagram/openai/openapi_key.txt"))
    output_rows = defaultdict(list)  # "account": list[event details]

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=50, channel='chrome')
        page = browser.new_page()
        page.goto("https://www.instagram.com/")
        print("Loaded page:", page.title())

        # Log in
        # page.get_by_role("button", name="Log in").click()
        username, password = get_login('scrapers/instagram/login.txt')
        page.get_by_role("textbox", name="username").fill(username)
        page.get_by_role("textbox", name="password").fill(password)
        wait(page, 600, 100)
        page.get_by_role("button").filter(has_not_text="Facebook").filter(has_text="Log in").click()
        wait(page, 600, 100)
        page.get_by_role("button").filter(has_text="Not now").click()
        print("Logged in")
        wait(page, 800, 200)

        urls = []
        # accounts = 'venen_0', '999_adj', #'quedup_toronto', 'venusinfoil', 'format.toronto', 'bsmt254toronto'
        accounts = '999_adj',
        # Visit accounts
        for account in accounts:
            print(f"Visiting account: {account}")
            # page.goto(f"https://www.instagram.com/stories/{account}/")  # Going here directly now has a confirmation
            page.goto(f"https://www.instagram.com/{account}/")
            wait(page, 800, 200)

            # Check out stories
            try:
                expect(page.get_by_role("button").get_by_alt_text(f"{account}'s profile picture")).to_be_visible()
            except AssertionError as e:
                # No stories
                print("No stories found")
                continue
            page.get_by_role("button").get_by_alt_text(f"{account}'s profile picture").click()
            wait(page, 1500, 200)

            i = 0
            while(True):
                output_rows[account].append({
                    'account': account,
                    'story_index': i,
                    'event_name': None,
                    'event_artist': None,
                    'event_location': None,
                    'event_date': None,
                    'event_time': None,
                    'event_notes': None,
                    'links': None
                })
                assert len(output_rows[account]) == i + 1

                # Save HTML for reference
                filename = os.path.join(html_dir, f"{account}_story_{i}.html")
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
                    output_rows[account][i]['links'] = ','.join(urls)

                # Save image to parse later
                event_info = {}
                page.screenshot(path=os.path.join(image_dir, f"{account}_story_{i}.png"))

                # Continue if there are more stories
                try:
                    expect(page.get_by_role('button', name='Next')).to_be_visible()
                except AssertionError as e:
                    # No more stories
                    print(f"{i + 1} storie(s) found")
                    break
                page.get_by_role('button', name='Next').click()
                wait(page, 1500, 100)
                i += 1
        browser.close()

    # Parse story screenshots
    for image_name in os.listdir(image_dir):
        if not image_name.endswith('.png'):
            continue
        image_path = os.path.join(image_dir, image_name)
        story_index = int(image_name.split('_')[-1][:-len('.png')])
        print(f"Parsing {image_name}...")
        account = image_name.split('_story_')[0]
        details = parse_image(openai_client, system_prompt, user_prompt, image_path)
        try:
            parsed_details: EventDetails = details.output[0].content[0].parsed
        except AttributeError:
            print("Could not parse:", image_path)
            continue
        output_rows[account][story_index]['event_name'] = parsed_details.event_name
        output_rows[account][story_index]['event_artist'] = parsed_details.artist
        output_rows[account][story_index]['event_location'] = parsed_details.location
        if parsed_details.start_date:
            output_rows[account][story_index]['event_date'] = parsed_details.start_date.split('T')[0]
            output_rows[account][story_index]['event_time'] = parsed_details.start_date.split('T')[1]
        output_rows[account][story_index]['event_notes'] = parsed_details.other_notes

        # Output to file
    with open(output_filename, "w", encoding="utf-8", newline="") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=['account', 'story_index', 'event_name', 'event_artist', 'event_location', 'event_date', 'event_time', 'event_notes', 'links'])
        writer.writeheader()
        for account in output_rows:
            for row in output_rows[account]:
                writer.writerow(row)
    print(f"Saved to {output_filename}")


def debug():
    user_prompt = read_file("scrapers/instagram/openai/image_parsing_prompt.txt")
    system_prompt = read_file("scrapers/instagram/openai/system_prompt.txt")
    system_prompt = system_prompt.format(datetime.datetime.today().strftime("%c"))  # Add current timestamp
    openai_client = OpenAI(api_key=read_file("scrapers/instagram/openai/openapi_key.txt"))

    image_dir = "/Users/kaz/Desktop"
    image_name = "Screenshot 2025-06-04 at 1.39.45 PM.png"
    # image_name = "Screenshot 2025-06-04 at 2.03.52 PM.png"
    image_path = os.path.join(image_dir, image_name)
    results = parse_image(openai_client, system_prompt, user_prompt, image_path)

    pass
    breakpoint()


if __name__ == "__main__":
    main()
    # debug()
