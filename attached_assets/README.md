# Thai Discord Shop Bot

A Discord bot shop system with product management, interactive purchase interface, and transaction history in Thai language.

## Features

- Interactive shop interface with buttons for product selection and quantity input
- Admin commands for product management (add/delete/edit)
- Both prefix commands (!) and slash commands (/) support
- Purchase history tracking
- Thai language support throughout
- Emoji-based product display
- Clear transaction records

## Setup

1. Make sure you have Python 3.8+ installed
2. Install required packages:
   ```
   pip install discord.py
   ```
3. Set up your Discord bot:
   - Go to [Discord Developer Portal](https://discord.com/developers/applications)
   - Create a new application
   - Go to the "Bot" tab and add a bot
   - Enable all Privileged Gateway Intents
   - Copy the bot token

4. Set the bot token as an environment variable:
   ```
   # On Windows:
   set DISCORD_BOT_TOKEN=your_token_here
   
   # On Linux/macOS:
   export DISCORD_BOT_TOKEN=your_token_here
   ```

5. Run the bot:
   ```
   python shopbot.py
   ```

## Bot Commands

### For All Users
- `!ร้าน [หมวด]` or `/ร้าน [หมวด]` - Open the shop to purchase items (category is optional)
  - Available categories: `money`, `weapon`, `item`, `car`, `fashion`, `เช่ารถ`
- `!สินค้าทั้งหมด [หมวด]` or `/สินค้าทั้งหมด [หมวด]` - View all available products (category is optional)
- `!ช่วยเหลือ` or `/ช่วยเหลือ` - Show help information

### For Administrators Only
- `!เพิ่มสินค้า [ชื่อ] [ราคา] [อีโมจิ] [หมวด]` or `/เพิ่มสินค้า` - Add a new product to the shop (category is optional, defaults to "item")
- `!ลบสินค้า [ชื่อ]` or `/ลบสินค้า` - Remove a product from the shop
- `!แก้ไขสินค้า [ชื่อ] [ชื่อใหม่] [ราคาใหม่] [อีโมจิใหม่] [หมวดใหม่]` or `/แก้ไขสินค้า` - Edit an existing product (parameters are optional)
- `!ประวัติ [จำนวน]` or `/ประวัติ` - View purchase history (default: 5 most recent entries)

Note: Administrator commands require the user to have Administrator permissions in the Discord server.

## Data Storage

The bot uses two JSON files for data storage:
- `products.json` - Stores product information (name, price, emoji, category)
- `history.json` - Records purchase history

## Required Discord Permissions

- Make sure the bot has the following permissions:
  - Send Messages
  - Embed Links
  - Read Message History
  - Add Reactions
  - Use External Emojis

- Ensure users who need administrator access have the "Administrator" permission in your Discord server

## Example Product Format

```json
[
  {
    "name": "น้ำเปล่า",
    "price": 10,
    "emoji": "💧",
    "category": "item"
  },
  {
    "name": "ปืนพก",
    "price": 5000,
    "emoji": "🔫",
    "category": "weapon"
  },
  {
    "name": "รถจี๊ป",
    "price": 50000,
    "emoji": "🚙",
    "category": "car"
  }
]
