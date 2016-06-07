from bs4 import BeautifulSoup, Comment, Declaration
import unirest
import re
from datetime import datetime, timedelta
from urllib2 import URLError
from ssl import SSLError

from news_sentiment import db
from models.article import Article
from articleMatcher import match


def isArticleText(element):
    """
    Found @
    http://stackoverflow.com/questions/1936466/beautifulsoup-grab-visible-webpage-text

    Given an html text element
    returns if the element is user visible
    """

    if element.parent.name in ['style', 'script', '[document]', 'head', 'title']:
        return False
    elif re.match('<!--.*-->', unicode(element)):
        return False
    elif type(element) is Comment or type(element) is Declaration:
        # BeautifulSoup wraps some elements in nicer data structures, gotta check tho
        return False
    elif len(unicode(element)) < 250:
        # Try to figure out if an article or not. This is purely by length. No shorties.
        return False
    return True


def scrapeGoogleArticle(articleSoup, edition):
    relatedLinkSoup = articleSoup.findAll('a', attrs={'class': 'esc-topic-link'})
    relatedLinks = []
    for link in relatedLinkSoup:
        # Can't figure out why I keep scraping 2 copies of every related link
        formattedLink = 'http://news.google.com' + link['href']
        if formattedLink not in relatedLinks:
            relatedLinks.append('http://news.google.com' + link['href'])

    articleUrl = articleSoup.find('a', attrs={'class': 'article'})['href']

    # Try to strip out just the name root source
    sourceSite = re.search('http://(.+?)\.(.+?)/(.+?)', articleUrl)
    if sourceSite:
        sourceSite = sourceSite.group(2)

    articleTitle = articleSoup.find('span', 'titletext').text

    # Try to strip out the date
    dateText = articleSoup.find('span', 'al-attribution-timestamp').text
    minsAgo = int(re.search(r'\d+', dateText).group())
    if dateText.lower().find('hour') != -1:
        minsAgo *= 60

    articleDate = datetime.utcnow() - timedelta(minutes=minsAgo)

    try:
        articleSourceResponse = unirest.get(articleUrl)
        if articleSourceResponse.code == 303:
            # NY times really not playing nice with scraping
            # Could use the selenium headless browser to get around this. Humph.
            articleSourceResponse = unirest.get(articleSourceResponse.headers.dict['location'])
            print "Ugh @ NYTimes redirect"
        articleSource = articleSourceResponse.body

        # Now we have to filter out all html on the page and just try to grab the visible text
        # Note: This is not as good as scraping just the article, but I do not have the time
        # to write a scraper for each website

        texts = BeautifulSoup(articleSource, 'html.parser').findAll(text=True)
        visibleTextList = filter(isArticleText, texts)

        article = Article(
            date=articleDate,
            title=articleTitle,
            site=sourceSite,
            url=articleUrl,
            relatedLinks=relatedLinks,
            newsEdition=edition,
            visibleTexts=visibleTextList,
            rawPage=articleSource
        )

        article.validate()
        match(article)

        return article
    except (SSLError, URLError, db.ValidationError) as ex:
        print "Failed to validate the article: " + article.title
        print "Because of " + str(ex)
        return None


def scrapeGoogleNews(edition):
    """

    :return: list of models.Article.Article
    """
    articles = []
    url = 'https://news.google.com/news/section?cf=all&pz=1&topic=n'
    source = unirest.get(url)
    soup = BeautifulSoup(source.body, 'html.parser')
    articleListSoup = soup.findAll('div', attrs={'class': 'blended-wrapper'})

    print "Scraping Google News: " + edition
    print str(len(articleListSoup)) + " articles to scrape."
    articleCount = 1

    for articleSoup in articleListSoup:
        print "Scraping article #" + str(articleCount)
        articleCount += 1
        article = scrapeGoogleArticle(articleSoup, edition)
        if article is not None:
            articles.append(article)

    print "Done scraping"
    return articles