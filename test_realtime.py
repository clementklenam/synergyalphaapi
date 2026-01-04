#!/usr/bin/env python3
"""
Simple test script for real-time price endpoints
"""
import asyncio
import websockets
import json
import requests
import time

BASE_URL = "http://localhost:8000"
WS_URL = "ws://localhost:8000"

def test_rest_endpoints():
    """Test REST API endpoints"""
    print("=" * 60)
    print("Testing REST API Endpoints")
    print("=" * 60)
    
    # Test 1: Single ticker
    print("\n1. Testing single ticker endpoint:")
    response = requests.get(f"{BASE_URL}/quote/realtime/AAPL")
    if response.status_code == 200:
        data = response.json()
        print(f"✅ AAPL Price: ${data.get('price'):.2f}")
        print(f"   Change: {data.get('change_percent', 0):.2f}%")
        print(f"   Volume: {data.get('volume', 0):,}")
    else:
        print(f"❌ Error: {response.status_code}")
    
    # Test 2: Multiple tickers
    print("\n2. Testing multiple tickers endpoint:")
    response = requests.get(
        f"{BASE_URL}/quote/realtime",
        params={'tickers': ['AAPL', 'MSFT', 'GOOGL']}
    )
    if response.status_code == 200:
        data = response.json()
        for ticker, quote in data.items():
            if quote:
                print(f"✅ {ticker}: ${quote.get('price', 0):.2f} ({quote.get('change_percent', 0):.2f}%)")
            else:
                print(f"⚠️  {ticker}: No data")
    else:
        print(f"❌ Error: {response.status_code}")
    
    # Test 3: Status endpoint
    print("\n3. Testing status endpoint:")
    response = requests.get(f"{BASE_URL}/quote/realtime/status")
    if response.status_code == 200:
        status = response.json()
        print(f"✅ Service running: {status.get('is_running')}")
        print(f"   Active subscriptions: {status.get('active_subscriptions')}")
        print(f"   Active tickers: {status.get('active_tickers')}")
        print(f"   Cached tickers: {status.get('cached_tickers')}")
    else:
        print(f"❌ Error: {response.status_code}")


async def test_websocket(ticker="AAPL", duration=10):
    """Test WebSocket endpoint"""
    print("\n" + "=" * 60)
    print(f"Testing WebSocket Endpoint for {ticker}")
    print("=" * 60)
    print(f"Connecting to {WS_URL}/ws/quote/{ticker}...")
    print(f"Will receive updates for {duration} seconds...\n")
    
    try:
        uri = f"{WS_URL}/ws/quote/{ticker}"
        async with websockets.connect(uri) as websocket:
            print("✅ Connected!")
            
            update_count = 0
            start_time = time.time()
            
            try:
                while time.time() - start_time < duration:
                    try:
                        message = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                        data = json.loads(message)
                        update_count += 1
                        
                        if data.get('type') == 'ping':
                            continue
                        
                        price_data = data.get('data', {})
                        print(f"[{update_count}] {data.get('ticker')}: "
                              f"${price_data.get('price', 0):.2f} "
                              f"({price_data.get('change_percent', 0):.2f}%) "
                              f"- Volume: {price_data.get('volume', 0):,}")
                        
                    except asyncio.TimeoutError:
                        print("⏳ Waiting for updates...")
                        continue
                        
            except websockets.exceptions.ConnectionClosed:
                print("\n⚠️  Connection closed by server")
            
            print(f"\n✅ Received {update_count} updates in {duration} seconds")
            
    except Exception as e:
        print(f"❌ Error: {e}")


if __name__ == "__main__":
    import sys
    
    print("\n" + "=" * 60)
    print("Real-Time Stock Price API Test")
    print("=" * 60)
    
    # Test REST endpoints
    test_rest_endpoints()
    
    # Test WebSocket if requested
    if len(sys.argv) > 1 and sys.argv[1] == "--websocket":
        ticker = sys.argv[2] if len(sys.argv) > 2 else "AAPL"
        duration = int(sys.argv[3]) if len(sys.argv) > 3 else 10
        asyncio.run(test_websocket(ticker, duration))
    else:
        print("\n" + "=" * 60)
        print("To test WebSocket, run:")
        print(f"  python test_realtime.py --websocket AAPL 10")
        print("=" * 60)
    
    print("\n✅ Testing complete!\n")

