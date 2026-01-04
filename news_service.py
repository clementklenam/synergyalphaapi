import asyncio
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
import yfinance as yf
from yfinance.exceptions import YFRateLimitError
import random
import aiohttp
from bs4 import BeautifulSoup
import re

logger = logging.getLogger(__name__)


class NewsService:
    """Service for fetching stock news using Yahoo Finance"""
    
    def __init__(self):
        self._semaphore = asyncio.Semaphore(3)  # Limit concurrent requests
        self._content_semaphore = asyncio.Semaphore(2)  # Limit concurrent content fetches
    
    async def get_news(self, ticker: str, limit: int = 10, include_content: bool = False) -> List[Dict[str, Any]]:
        """
        Fetch news articles for a ticker
        
        Args:
            ticker: Stock ticker symbol
            limit: Maximum number of articles to return (default: 10)
            
        Returns:
            List of news articles with formatted data
        """
        async with self._semaphore:
            try:
                # Add small random delay to avoid rate limits
                await asyncio.sleep(random.uniform(0.1, 0.3))
                
                stock = yf.Ticker(ticker.upper())
                news_articles = stock.news
                
                if not news_articles:
                    logger.info(f"No news found for {ticker}")
                    return []
                
                # Format and limit articles
                formatted_news = []
                for article in news_articles[:limit]:
                    formatted_article = await self._format_article(article, ticker, include_content)
                    formatted_news.append(formatted_article)
                
                logger.debug(f"Fetched {len(formatted_news)} news articles for {ticker}")
                return formatted_news
                
            except YFRateLimitError:
                logger.warning(f"Rate limit hit for {ticker} news, backing off")
                await asyncio.sleep(5)
                return []
            except Exception as e:
                logger.error(f"Error fetching news for {ticker}: {e}")
                return []
    
    async def _format_article(self, article: Dict[str, Any], ticker: str, include_content: bool = False) -> Dict[str, Any]:
        """
        Format a news article from yfinance format to our API format
        
        Args:
            article: Raw article data from yfinance
            ticker: Stock ticker symbol
            
        Returns:
            Formatted article dictionary
        """
        content = article.get('content', {})
        thumbnail = content.get('thumbnail', {})
        provider = content.get('provider', {})
        canonical_url = content.get('canonicalUrl', {})
        
        # Extract thumbnail URL (prefer smaller size for faster loading)
        thumbnail_url = None
        if thumbnail:
            resolutions = thumbnail.get('resolutions', [])
            if resolutions:
                # Prefer 170x128, fallback to original
                thumbnail_url = next(
                    (r.get('url') for r in resolutions if r.get('tag') == '170x128'),
                    thumbnail.get('originalUrl')
                )
            else:
                thumbnail_url = thumbnail.get('originalUrl')
        
        formatted = {
            "id": article.get('id'),
            "ticker": ticker.upper(),
            "title": content.get('title', ''),
            "summary": content.get('summary', ''),
            "description": content.get('description', ''),
            "publish_date": content.get('pubDate'),
            "display_time": content.get('displayTime'),
            "url": canonical_url.get('url') if canonical_url else None,
            "thumbnail_url": thumbnail_url,
            "provider": provider.get('displayName', ''),
            "provider_url": provider.get('url', ''),
            "is_editor_pick": content.get('metadata', {}).get('editorsPick', False),
            "content_type": content.get('contentType', ''),
        }
        
        # Fetch article content if requested
        if include_content and formatted["url"]:
            article_content = await self._fetch_article_content(formatted["url"])
            formatted["content"] = article_content
        
        return formatted
    
    async def _fetch_article_content(self, url: str) -> Optional[str]:
        """
        Fetch and extract article content from URL
        
        Args:
            url: Article URL
            
        Returns:
            Extracted article text content, or None if extraction fails
        """
        async with self._content_semaphore:
            try:
                timeout = aiohttp.ClientTimeout(total=10)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(url, headers={
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                    }) as response:
                        if response.status != 200:
                            logger.warning(f"Failed to fetch article content: HTTP {response.status}")
                            return None
                        
                        html = await response.text()
                        soup = BeautifulSoup(html, 'lxml')
                        
                        # Remove script and style elements
                        for script in soup(["script", "style", "nav", "header", "footer", "aside"]):
                            script.decompose()
                        
                        # Try to find main article content
                        # Common patterns for article content
                        article_selectors = [
                            'article',
                            '[role="article"]',
                            '.article-body',
                            '.article-content',
                            '.post-content',
                            '.entry-content',
                            'main article',
                            '.caas-body',
                            '#article-body',
                        ]
                        
                        article_text = None
                        for selector in article_selectors:
                            article_elem = soup.select_one(selector)
                            if article_elem:
                                article_text = article_elem.get_text(separator='\n', strip=True)
                                if len(article_text) > 200:  # Ensure we got substantial content
                                    break
                        
                        # Fallback: get all paragraphs
                        if not article_text or len(article_text) < 200:
                            paragraphs = soup.find_all('p')
                            article_text = '\n\n'.join([p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True)])
                        
                        # Clean up text
                        if article_text:
                            # Remove excessive whitespace
                            article_text = re.sub(r'\n{3,}', '\n\n', article_text)
                            article_text = article_text.strip()
                            
                            # Only return if we have substantial content
                            if len(article_text) > 100:
                                return article_text
                        
                        return None
                        
            except asyncio.TimeoutError:
                logger.warning(f"Timeout fetching article content from {url}")
                return None
            except Exception as e:
                logger.warning(f"Error fetching article content from {url}: {e}")
                return None
    
    async def get_news_batch(self, tickers: List[str], limit: int = 10, include_content: bool = False) -> Dict[str, List[Dict[str, Any]]]:
        """
        Fetch news for multiple tickers concurrently
        
        Args:
            tickers: List of stock ticker symbols
            limit: Maximum number of articles per ticker
            
        Returns:
            Dictionary mapping ticker to list of news articles
        """
        tasks = [self.get_news(ticker, limit, include_content) for ticker in tickers]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        news_dict = {}
        for ticker, result in zip(tickers, results):
            if isinstance(result, Exception):
                logger.error(f"Error fetching news for {ticker}: {result}")
                news_dict[ticker.upper()] = []
            else:
                news_dict[ticker.upper()] = result
        
        return news_dict


# Global instance
_news_service: Optional[NewsService] = None


def get_news_service() -> NewsService:
    """Get the global NewsService instance"""
    global _news_service
    if _news_service is None:
        _news_service = NewsService()
    return _news_service

