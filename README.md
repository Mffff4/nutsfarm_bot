# NutsFarm Bot

[🇷🇺 Русский](README-RU.md)

[![Bot Link](https://img.shields.io/badge/Telegram_Bot-Link-blue?style=for-the-badge&logo=Telegram&logoColor=white)](https://t.me/nutsfarm_bot/nutscoin?startapp=ref_DTGYWCIWEZSAGUB)
[![Channel Link](https://img.shields.io/badge/Telegram_Channel-Link-blue?style=for-the-badge&logo=Telegram&logoColor=white)](https://t.me/+pwYQJQz0zyM0MmMy)
[![Channel Link](https://img.shields.io/badge/Bot_Collection-Link-blue?style=for-the-badge&logo=Telegram&logoColor=white)](https://t.me/+uF4lQD9ZEUE4NGUy)

---

## 📑 Table of Contents
1. [Description](#description)
2. [Key Features](#key-features)
3. [Installation](#installation)
   - [Quick Start](#quick-start)
   - [Manual Installation](#manual-installation)
4. [Settings](#settings)
5. [Support and Donations](#support-and-donations)
6. [Contact](#contact)

---

## 📜 Description
**NutsFarm Bot** is an automated bot for interacting with NutsFarm. The bot automatically completes tasks, collects rewards, manages farming, and monitors streaks, maximizing your NUTS earnings.

---

## 🌟 Key Features
- 🔄 **Automatic Farming** — bot independently starts and collects farming rewards
- 🎯 **Task Completion** — automatic completion of all available tasks
- 📱 **Channel Subscriptions** — automatic subscription to Telegram channels with notification muting
- 📊 **Streak Management** — daily collection of streak rewards
- 📖 **Story Reading** — automatic viewing and collection of story rewards
- ⏰ **Smart Scheduling** — bot wakes up exactly when farming ends
- 🔐 **Proxy Support** — ability to work through proxies for security
- 📈 **Multi-Account** — simultaneous operation with multiple accounts

---

## 🛠️ Installation

### Quick Start
1. **Download the project:**
   ```bash
   git clone https://github.com/Mffff4/nutsfarm_bot.git
   cd nutsfarm_bot
   ```

2. **Install dependencies:**
   - **Windows**:
     ```bash
     run.bat
     ```
   - **Linux**:
     ```bash
     run.sh
     ```

3. **Get API keys:**
   - Go to [my.telegram.org](https://my.telegram.org) and get your `API_ID` and `API_HASH`
   - Add this data to the `.env` file

4. **Run the bot:**
   ```bash
   python main.py -a 3  # Start the bot
   ```

### Manual Installation
1. **Linux:**
   ```bash
   sudo sh install.sh
   python3 -m venv venv
   source venv/bin/activate
   pip3 install -r requirements.txt
   cp .env-example .env
   nano .env  # Add your API_ID and API_HASH
   python3 main.py
   ```

2. **Windows:**
   ```bash
   python -m venv venv
   venv\Scripts\activate
   pip install -r requirements.txt
   copy .env-example .env
   python main.py
   ```

---

## ⚙️ Settings

| Parameter                    | Default Value         | Description                                                  |
|----------------------------|----------------------|----------------------------------------------------------|
| **API_ID**                 |                      | Application ID from my.telegram.org                      |
| **API_HASH**               |                      | Application hash from my.telegram.org                    |
| **USE_PROXY_FROM_FILE**    | False                | Use proxy from file                                     |
| **REF_ID**                 | "DTGYWCIWEZSAGUB"    | Referral code for registration                          |
| **ENABLE_CHANNEL_SUBSCRIPTIONS** | True           | Enable channel subscriptions                            |
| **REQUEST_TIMEOUT**        | [30, 60]             | Request timeout (min, max) in seconds                   |
| **RETRY_DELAY**            | [3, 10]              | Delay between retries (min, max) in seconds             |
| **MAX_RETRIES**            | 5                    | Maximum number of retries                               |
| **ACTION_DELAY**           | [2, 4]               | Delay between actions (min, max) in seconds             |
| **SLEEP_TIME**             | [3600, 7200]         | Sleep time when no actions (min, max) in seconds        |
| **LOG_PROXY**              | True                 | Log proxy usage                                         |
| **LOG_USER_AGENT**         | True                 | Log User-Agent                                          |

---
## 💰 Support and Donations

Support the development using cryptocurrencies:

| Currency              | Wallet Address                                                                     |
|----------------------|------------------------------------------------------------------------------------|
| Bitcoin (BTC)|bc1qt84nyhuzcnkh2qpva93jdqa20hp49edcl94nf6| 
| Ethereum (ETH)|0xc935e81045CAbE0B8380A284Ed93060dA212fa83| 
|TON|UQBlvCgM84ijBQn0-PVP3On0fFVWds5SOHilxbe33EDQgryz|
| Binance Coin (BNB)|0xc935e81045CAbE0B8380A284Ed93060dA212fa83| 
| Solana (SOL)|3vVxkGKasJWCgoamdJiRPy6is4di72xR98CDj2UdS1BE| 
| Ripple (XRP)|rPJzfBcU6B8SYU5M8h36zuPcLCgRcpKNB4| 
| Dogecoin (DOGE)|DST5W1c4FFzHVhruVsa2zE6jh5dznLDkmW| 
| Polkadot (DOT)|1US84xhUghAhrMtw2bcZh9CXN3i7T1VJB2Gdjy9hNjR3K71| 
| Litecoin (LTC)|ltc1qcg8qesg8j4wvk9m7e74pm7aanl34y7q9rutvwu| 
| Matic|0xc935e81045CAbE0B8380A284Ed93060dA212fa83| 
| Tron (TRX)|TQkDWCjchCLhNsGwr4YocUHEeezsB4jVo5| 
---

## 📞 Contact

If you have any questions or suggestions:
- **Telegram**: [Join our channel](https://t.me/+pwYQJQz0zyM0MmMy)

---

## ⚠️ Disclaimer

This software is provided "as is" without any warranties. By using this bot, you accept full responsibility for its use and any consequences that may arise.

The author is not responsible for:
- Any direct or indirect damages related to the use of the bot
- Possible violations of third-party service terms of use
- Account blocking or access restrictions

Use the bot at your own risk and in compliance with applicable laws and third-party service terms of use.

