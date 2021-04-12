import asyncio
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from timeit import default_timer
from urllib.parse import urlparse

import click
import requests
from bs4 import BeautifulSoup

already_visited_urls = []


def fetch(session, url):
    """
    This function will check if the URL has been visited before
    if not, it will use the request object to get the page

    Parameters
    ----------
    session : reqeuests
        Requests object
    url : str
        URL

    Returns
    -------
    str
        The content of the url
    """
    url = url.strip("/")
    if url not in already_visited_urls:
        already_visited_urls.append(url)
        with session.get(url) as response:
            data = response.text
            if response.status_code != 200:
                return None
            print(url)
            return data
    return None


@dataclass(frozen=True)
class URLExtractResult:
    host: str
    domain: str
    suffix: str


def tdl_extract(url):
    """
    This function will analyse a URL and pass the required attributes

    Parameters
    ----------
    url : str
        URL

    Returns
    -------
    URLExtractResult
        Object containing the host, domain and suffix attributes of the URL
    """
    t = urlparse(url).netloc
    host = ".".join(t.split(".")[1:])
    domain = host.split(".")[0]
    suffix = ".".join(t.split(".")[2:])
    return URLExtractResult(host=host, domain=domain, suffix=suffix)


async def initiate_crawler(base_url, no_of_workers=10):
    """
    This function will initiate the processes required to begin the crawling tasks

    Parameters
    ----------
    base_url : str
        URL
    no_of_workers: int
        The number of workers to pass into the ThreadPoolExecutor. Uses a default of 10 if nothing is passed.
    """
    # Check if base_url has a scheme attribute
    if not urlparse(base_url).scheme:
        base_url = "http://" + base_url
    base_url_details = tdl_extract(base_url)
    request = requests.get(base_url)
    if request.status_code == 200 and request.content:
        page_content = request.content
        already_visited_urls.append(base_url)
        with ThreadPoolExecutor(max_workers=no_of_workers) as executor:
            with requests.Session() as session:
                await crawl_page(executor, session, page_content, base_url_details)


async def crawl_page(executor, session, html_content, base_url_details):
    """
    This function will crawl the content of the page and decide whether to go fetch more page
    provided new links are found on the page.

    Parameters
    ----------
    executor : ThreadPoolExecutor
        Instance of the ThreadPoolExecutor
    session: int
        The requests instance initiated with the ThreadPoolExecutor
    html_content: str
        The content of the page
    base_url_details: URLExtractResult
        The attributes of the base URL
    """

    soup = BeautifulSoup(html_content, "html.parser")
    
    # Build regex based on the base URL's attributes, domain and suffix
    regex = (
        "(http:\\//\\//www\\.|https:\\//\\//www\\.|http:\\//\\//|https:\\//\\//)?"
        + "[a-z0-9]+([\\-\\.]"
        + base_url_details.domain
        + "+)\\."
        + base_url_details.suffix
        + "?(\\//.*)?"
    )
    # Regex ensures we are only searching for links within the base URL's domain
    links = soup.find_all("a", attrs={"href": re.compile(regex)})
    loop = asyncio.get_event_loop()
    tasks = [
        loop.run_in_executor(
            executor, fetch, *(session, link["href"])  # Allows us to pass in multiple arguments to `fetch`
        )
        for link in links
    ]

    for response in await asyncio.gather(*tasks):
        if response:
            await crawl_page(executor, session, response, base_url_details)


def is_valid_url(value):
    """
    This function will validate if value is a valid URL

    Parameters
    ----------
    value : str
        URL

    Returns
    -------
    bool
        True or False
    """

    # Regex to check valid URL
    regex = (
        "(?:(?:https?|http):\\//\\//|www\\.)?"
        + "[a-zA-Z0-9@:%._\\+~#?&//=]"
        + "{2,256}\\.[a-z]"
        + "{2,6}\\b([-a-zA-Z0-9@:%"
        + "._\\+~#?&//=]*)"
    )  # noqa

    # Compile the ReGex
    p = re.compile(regex)

    # If the string is empty
    # return false
    if value is None:
        return False

    # Return if the string
    # matched the ReGex
    if re.search(p, value):
        return True
    else:
        return False


@click.command()
@click.argument("url")
@click.option("--workers", "-n")
def main(url, workers):
    # Validate that workers is a valid number
    try:
        workers = int(workers)
    except (ValueError, TypeError):
        print("Enter a valid amount of worker")
        sys.exit(0)

    if workers <= 0:
        print("Ensure you number of workers is greater than 0")
        sys.exit(0)

    # Validate that url is valid
    if not is_valid_url(url):
        print("Enter a valid url")
        sys.exit(0)

    loop = asyncio.get_event_loop()
    future = asyncio.ensure_future(initiate_crawler(url, workers))
    loop.run_until_complete(future)
    sys.exit(0)


if __name__ == "__main__":
    main()
