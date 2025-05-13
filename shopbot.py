import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput
import json
import os
from datetime import datetime
from pathlib import Path
import re
import logging
from server import keep_alive

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('shopbot')

# Get the directory of the current script to ensure file paths are correct
SCRIPT_DIR = Path(__file__).parent.absolute()
PRODUCTS_FILE = SCRIPT_DIR / "products.json"
HISTORY_FILE = SCRIPT_DIR / "history.json"

# Setup bot with necessary intents
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

def load_products():
    """Load product data from the JSON file"""
    try:
        with open(PRODUCTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        logger.error(f"Products file not found at {PRODUCTS_FILE}")
        return []
    except json.JSONDecodeError:
        logger.error(f"Invalid JSON in products file at {PRODUCTS_FILE}")
        return []

def save_products(products):
    """Save product data to the JSON file"""
    with open(PRODUCTS_FILE, "w", encoding="utf-8") as f:
        json.dump(products, f, ensure_ascii=False, indent=2)

def load_history():
    """Load purchase history from the JSON file"""
    if not HISTORY_FILE.exists():
        HISTORY_FILE.touch()
        return []
        
    try:
        history = []
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        history.append(json.loads(line))
                    except json.JSONDecodeError:
                        logger.error(f"Invalid JSON in history file: {line}")
        return history
    except Exception as e:
        logger.error(f"Error loading history: {e}")
        return []

def log_purchase(user, items, total_price):
    """Log purchase history to the JSON file"""
    # Create the history file if it doesn't exist
    if not HISTORY_FILE.exists():
        HISTORY_FILE.touch()
        
    try:
        with open(HISTORY_FILE, "a", encoding="utf-8") as f:
            data = {
                "user": str(user),
                "items": items,
                "total": total_price,
                "timestamp": datetime.now().isoformat()
            }
            f.write(json.dumps(data, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.error(f"Error logging purchase: {e}")

class QuantityModal(Modal):
    """Modal for entering product quantity"""
    def __init__(self, product_index, product):
        super().__init__(title=f"จำนวน {product['name']}")
        self.product_index = product_index
        self.product = product
        self.quantity = None
        
        # Create text input for quantity
        self.quantity_input = TextInput(
            label=f"ใส่จำนวน {product['name']} ที่ต้องการ",
            placeholder="ใส่จำนวน",
            required=True,
            min_length=1,
            max_length=3,
            default="1"
        )
        self.add_item(self.quantity_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            # Convert input to integer
            quantity = int(self.quantity_input.value)
            if quantity < 0:
                await interaction.response.send_message("❌ จำนวนต้องมากกว่าหรือเท่ากับ 0", ephemeral=True)
                return
            elif quantity > 100:
                await interaction.response.send_message("❌ จำนวนต้องไม่เกิน 100", ephemeral=True)
                return
                
            self.quantity = quantity
            await interaction.response.defer()
        except ValueError:
            await interaction.response.send_message("❌ กรุณาใส่จำนวนเป็นตัวเลขเท่านั้น", ephemeral=True)

class ShopView(View):
    """Main shop view with product buttons"""
    def __init__(self, category=None):
        super().__init__(timeout=None)
        self.all_products = load_products()
        
        # Filter products by category if specified
        if category:
            self.products = [p for p in self.all_products if p.get('category', '') == category]
        else:
            self.products = self.all_products
            
        self.quantities = [0] * len(self.products)
        
        # Create buttons for each product
        for idx, product in enumerate(self.products):
            self.add_item(ProductButton(idx, self.products))
            
        # Add reset and confirm buttons
        self.add_item(ResetButton())
        self.add_item(ConfirmButton(self.products))

class ProductButton(Button):
    """Button for each product in the shop"""
    def __init__(self, index, products):
        self.index = index
        product = products[index]
        label = f"{product['emoji']} {product['name']} - {product['price']}฿"
        super().__init__(label=label, style=discord.ButtonStyle.primary, custom_id=f"product_{index}")

    async def callback(self, interaction: discord.Interaction):
        view: ShopView = self.view
        
        # Create modal for quantity input
        modal = QuantityModal(self.index, view.products[self.index])
        await interaction.response.send_modal(modal)
        # Wait for modal to be submitted
        await modal.wait()
        
        if modal.quantity is not None:
            # Update quantity in view
            view.quantities[self.index] = modal.quantity
            
            # Generate summary of selected items
            lines = []
            for i, qty in enumerate(view.quantities):
                if qty > 0:
                    p = view.products[i]
                    lines.append(f"{p['emoji']} {p['name']} - {p['price']}฿ x {qty} = {p['price'] * qty}฿")
            
            summary = "\n".join(lines) or "ยังไม่ได้เลือกสินค้า"
            total = sum(view.products[i]['price'] * qty for i, qty in enumerate(view.quantities))
            
            message = f"🛍️ รายการที่เลือก:\n{summary}\n\n💵 ยอดรวม: {total}฿"
            await interaction.message.edit(content=message, view=view)

class ResetButton(Button):
    """Button to reset the cart"""
    def __init__(self):
        super().__init__(label="🗑️ ล้างตะกร้า", style=discord.ButtonStyle.danger, custom_id="reset")

    async def callback(self, interaction: discord.Interaction):
        view: ShopView = self.view
        view.quantities = [0] * len(view.products)
        await interaction.response.edit_message(content="🛍️ รายการที่เลือก:\nยังไม่ได้เลือกสินค้า", view=view)

class ConfirmButton(Button):
    """Button to confirm the purchase"""
    def __init__(self, products):
        super().__init__(label="✅ ยืนยันการซื้อ", style=discord.ButtonStyle.success, custom_id="confirm")
        self.products = products

    async def callback(self, interaction: discord.Interaction):
        view: ShopView = self.view
        total_price = sum(self.products[i]['price'] * qty for i, qty in enumerate(view.quantities))
        
        # Check if cart is empty
        if total_price == 0:
            await interaction.response.send_message("❗ กรุณาเลือกสินค้าก่อน", ephemeral=True)
            return
            
        # Generate receipt
        lines = []
        items = []
        for i, qty in enumerate(view.quantities):
            if qty > 0:
                p = self.products[i]
                total = p['price'] * qty
                lines.append(f"{p['emoji']} {p['name']} - {p['price']}฿ x {qty} = {total}฿")
                items.append({"name": p["name"], "qty": qty, "price": p["price"]})
        
        # Log the purchase and generate receipt
        try:
            log_purchase(interaction.user, items, total_price)
            summary = "\n".join(lines)
            embed = discord.Embed(
                title="🧾 ใบเสร็จรับเงิน",
                description=f"**ลูกค้า:** {interaction.user.mention}\n**วันที่:** {datetime.now().strftime('%d/%m/%Y %H:%M')}",
                color=0x00ff00
            )
            embed.add_field(name="รายการสินค้า", value=summary, inline=False)
            embed.add_field(name="ยอดรวม", value=f"💵 {total_price}฿", inline=False)
            embed.set_footer(text="ขอบคุณที่ใช้บริการ! 🙏")
            
            # แสดงใบเสร็จสำหรับผู้ซื้อ (แสดงเฉพาะผู้ซื้อเท่านั้น)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
            # สร้างใบเสร็จสำหรับแสดงในแชทสาธารณะและให้แอดมินเห็น
            public_embed = discord.Embed(
                title="🧾 ใบเสร็จรับเงิน",
                description=f"**ลูกค้า:** {interaction.user.mention}\n**วันที่:** {datetime.now().strftime('%d/%m/%Y %H:%M')}",
                color=0x00ff00
            )
            public_embed.add_field(name="รายการสินค้า", value=summary, inline=False)
            public_embed.add_field(name="ยอดรวม", value=f"💵 {total_price}฿", inline=False)
            
            # แสดง QR Code สำหรับชำระเงิน
            qr_embed = discord.Embed(
                title="📲 กรุณาสแกน QR Code เพื่อชำระเงิน",
                description=f"**ลูกค้า:** {interaction.user.mention}\n**ยอดชำระ:** 💵 {total_price}฿\n**ธนาคาร:** SCB (ไทยพาณิชย์)",
                color=0x4f0099
            )
            qr_embed.set_image(url="https://media.discordapp.net/attachments/1177559485137555456/1297159106787934249/QRCodeSCB.png?ex=6823d54f&is=682283cf&hm=10acdea9e554c0c107119f230b8a9122498dc5a240e4e24080f3fd7f204c9df9&format=webp&quality=lossless&width=760&height=760")
            qr_embed.set_footer(text="กรุณาโอนเงินและแคปหลักฐานส่งให้แอดมิน")
            
            # ส่งทั้งใบเสร็จสาธารณะและ QR Code ในข้อความเดียวกัน
            await interaction.followup.send(embeds=[public_embed, qr_embed])
            
            # Reset the cart
            view.quantities = [0] * len(view.products)
            await interaction.message.edit(content="🛍️ รายการที่เลือก:\nยังไม่ได้เลือกสินค้า", view=view)
        except Exception as e:
            logger.error(f"Error generating receipt: {e}")
            await interaction.response.send_message(f"❌ เกิดข้อผิดพลาด: {str(e)}", ephemeral=True)

@bot.event
async def on_ready():
    """Event triggered when the bot is ready"""
    logger.info(f"Bot is ready! Logged in as {bot.user}")
    
    # Create history file if it doesn't exist
    if not HISTORY_FILE.exists():
        HISTORY_FILE.touch()
        logger.info(f"Created history file at {HISTORY_FILE}")
    
    # Register slash commands
    try:
        logger.info("Registering slash commands...")
        # Shop Commands
        await bot.tree.sync()
        logger.info("Slash commands registered successfully!")
    except Exception as e:
        logger.error(f"Error registering slash commands: {e}")

@bot.command(name="money")
async def shop_money(ctx):
    """Command to open the money category shop"""
    await shop(ctx, "money")

@bot.command(name="เงิน")
async def shop_money_th(ctx):
    """Command to open the money category shop (Thai)"""
    await shop(ctx, "money")

@bot.command(name="weapon")
async def shop_weapon(ctx):
    """Command to open the weapon category shop"""
    await shop(ctx, "weapon")
    
@bot.command(name="อาวุธ")
async def shop_weapon_th(ctx):
    """Command to open the weapon category shop (Thai)"""
    await shop(ctx, "weapon")

@bot.command(name="item")
async def shop_item(ctx):
    """Command to open the item category shop"""
    await shop(ctx, "item")
    
@bot.command(name="ไอเทม")
async def shop_item_th(ctx):
    """Command to open the item category shop (Thai)"""
    await shop(ctx, "item")

@bot.command(name="car")
async def shop_car(ctx):
    """Command to open the car category shop"""
    await shop(ctx, "car")
    
@bot.command(name="รถ")
async def shop_car_th(ctx):
    """Command to open the car category shop (Thai)"""
    await shop(ctx, "car")

@bot.command(name="fashion")
async def shop_fashion(ctx):
    """Command to open the fashion category shop"""
    await shop(ctx, "fashion")
    
@bot.command(name="แฟชั่น")
async def shop_fashion_th(ctx):
    """Command to open the fashion category shop (Thai)"""
    await shop(ctx, "fashion")

@bot.command(name="เช่ารถ")
async def shop_rentcar(ctx):
    """Command to open the car rental category shop"""
    await shop(ctx, "เช่ารถ")

@bot.command(name="ร้าน")
async def shop_command(ctx, category=None):
    """Open the shop interface with optional category filter"""
    await shop(ctx, category)

@bot.tree.command(name="ร้าน", description="เปิดร้านค้า")
async def shop_slash(interaction: discord.Interaction, หมวด: str = None):
    """Slash command to open the shop interface"""
    view = ShopView(หมวด)
    await interaction.response.send_message("🛍️ รายการที่เลือก:\nยังไม่ได้เลือกสินค้า", view=view)

async def shop(ctx, category=None):
    """Function to display the shop interface"""
    view = ShopView(category)
    await ctx.send("🛍️ รายการที่เลือก:\nยังไม่ได้เลือกสินค้า", view=view)

@bot.command(name="สินค้าทั้งหมด")
async def all_products(ctx, category=None):
    """Display all products, optionally filtered by category"""
    products = load_products()
    
    if category:
        products = [p for p in products if p.get('category', '') == category]
        if not products:
            await ctx.send(f"❌ ไม่พบสินค้าในหมวด '{category}'")
            return
    
    # Create embeds for products (max 25 fields per embed)
    embeds = []
    current_embed = discord.Embed(title="🛒 รายการสินค้าทั้งหมด", color=0x3498db)
    if category:
        current_embed.description = f"หมวด: {category}"
    
    # Group products by category for better organization
    categories = {}
    for p in products:
        cat = p.get('category', 'ไม่มีหมวด')
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(p)
    
    # Add fields for each category
    field_count = 0
    for cat, cat_products in categories.items():
        # If adding this category would exceed the field limit, create a new embed
        if field_count + 1 + len(cat_products) > 25:
            embeds.append(current_embed)
            current_embed = discord.Embed(title="🛒 รายการสินค้าทั้งหมด (ต่อ)", color=0x3498db)
            field_count = 0
        
        # Add category header
        cat_header = f"**{cat.upper()}**"
        current_embed.add_field(name=cat_header, value="────────────────", inline=False)
        field_count += 1
        
        # Add products in this category
        for p in cat_products:
            current_embed.add_field(
                name=f"{p['emoji']} {p['name']}",
                value=f"ราคา: {p['price']}฿",
                inline=True
            )
            field_count += 1
    
    embeds.append(current_embed)
    
    # Send all embeds
    for embed in embeds:
        await ctx.send(embed=embed)

@bot.tree.command(name="สินค้าทั้งหมด", description="แสดงรายการสินค้าทั้งหมด")
async def all_products_slash(interaction: discord.Interaction, หมวด: str = None):
    """Slash command to display all products"""
    products = load_products()
    
    if หมวด:
        products = [p for p in products if p.get('category', '') == หมวด]
        if not products:
            await interaction.response.send_message(f"❌ ไม่พบสินค้าในหมวด '{หมวด}'")
            return
    
    # Create embeds for products (max 25 fields per embed)
    embeds = []
    current_embed = discord.Embed(title="🛒 รายการสินค้าทั้งหมด", color=0x3498db)
    if หมวด:
        current_embed.description = f"หมวด: {หมวด}"
    
    # Group products by category for better organization
    categories = {}
    for p in products:
        cat = p.get('category', 'ไม่มีหมวด')
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(p)
    
    # Add fields for each category
    field_count = 0
    for cat, cat_products in categories.items():
        # If adding this category would exceed the field limit, create a new embed
        if field_count + 1 + len(cat_products) > 25:
            embeds.append(current_embed)
            current_embed = discord.Embed(title="🛒 รายการสินค้าทั้งหมด (ต่อ)", color=0x3498db)
            field_count = 0
        
        # Add category header
        cat_header = f"**{cat.upper()}**"
        current_embed.add_field(name=cat_header, value="────────────────", inline=False)
        field_count += 1
        
        # Add products in this category
        for p in cat_products:
            current_embed.add_field(
                name=f"{p['emoji']} {p['name']}",
                value=f"ราคา: {p['price']}฿",
                inline=True
            )
            field_count += 1
    
    embeds.append(current_embed)
    
    # Send first embed immediately, then follow up with the rest
    await interaction.response.send_message(embed=embeds[0])
    for embed in embeds[1:]:
        await interaction.followup.send(embed=embed)

@bot.command(name="เพิ่มสินค้า")
@commands.has_permissions(administrator=True)
async def add_product(ctx, name, price: int, emoji, category="item"):
    """Add a new product to the shop (admin only)"""
    products = load_products()
    
    # Check if product already exists
    if any(p['name'] == name for p in products):
        await ctx.send(f"❌ สินค้า '{name}' มีอยู่แล้ว")
        return
    
    # Add the new product
    products.append({
        "name": name,
        "price": price,
        "emoji": emoji,
        "category": category
    })
    
    save_products(products)
    await ctx.send(f"✅ เพิ่มสินค้า {emoji} {name} ราคา {price}฿ ในหมวด {category} เรียบร้อยแล้ว")

@bot.tree.command(name="เพิ่มสินค้า", description="เพิ่มสินค้าใหม่ (สำหรับแอดมินเท่านั้น)")
@commands.has_permissions(administrator=True)
async def add_product_slash(
    interaction: discord.Interaction, 
    ชื่อ: str, 
    ราคา: int, 
    อีโมจิ: str, 
    หมวด: str = "item"
):
    """Slash command to add a new product"""
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ คุณไม่มีสิทธิ์ใช้คำสั่งนี้", ephemeral=True)
        return
        
    products = load_products()
    
    # Check if product already exists
    if any(p['name'] == ชื่อ for p in products):
        await interaction.response.send_message(f"❌ สินค้า '{ชื่อ}' มีอยู่แล้ว", ephemeral=True)
        return
    
    # Add the new product
    products.append({
        "name": ชื่อ,
        "price": ราคา,
        "emoji": อีโมจิ,
        "category": หมวด
    })
    
    save_products(products)
    await interaction.response.send_message(f"✅ เพิ่มสินค้า {อีโมจิ} {ชื่อ} ราคา {ราคา}฿ ในหมวด {หมวด} เรียบร้อยแล้ว")

@bot.command(name="ลบสินค้า")
@commands.has_permissions(administrator=True)
async def delete_product(ctx, *, name):
    """Delete a product from the shop (admin only)"""
    products = load_products()
    
    # Find the product
    product = next((p for p in products if p['name'] == name), None)
    if not product:
        await ctx.send(f"❌ ไม่พบสินค้า '{name}'")
        return
    
    # Remove the product
    products.remove(product)
    save_products(products)
    await ctx.send(f"✅ ลบสินค้า {product['emoji']} {name} เรียบร้อยแล้ว")

@bot.tree.command(name="ลบสินค้า", description="ลบสินค้า (สำหรับแอดมินเท่านั้น)")
@commands.has_permissions(administrator=True)
async def delete_product_slash(interaction: discord.Interaction, ชื่อ: str):
    """Slash command to delete a product"""
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ คุณไม่มีสิทธิ์ใช้คำสั่งนี้", ephemeral=True)
        return
        
    products = load_products()
    
    # Find the product
    product = next((p for p in products if p['name'] == ชื่อ), None)
    if not product:
        await interaction.response.send_message(f"❌ ไม่พบสินค้า '{ชื่อ}'", ephemeral=True)
        return
    
    # Remove the product
    products.remove(product)
    save_products(products)
    await interaction.response.send_message(f"✅ ลบสินค้า {product['emoji']} {ชื่อ} เรียบร้อยแล้ว")

@bot.command(name="แก้ไขสินค้า")
@commands.has_permissions(administrator=True)
async def edit_product(ctx, name, new_name=None, new_price=None, new_emoji=None, new_category=None):
    """Edit an existing product (admin only)"""
    products = load_products()
    
    # Find the product
    product_idx = next((i for i, p in enumerate(products) if p['name'] == name), None)
    if product_idx is None:
        await ctx.send(f"❌ ไม่พบสินค้า '{name}'")
        return
    
    product = products[product_idx]
    
    # Update the product
    if new_name:
        product['name'] = new_name
    if new_price:
        try:
            product['price'] = int(new_price)
        except ValueError:
            await ctx.send("❌ ราคาต้องเป็นตัวเลขเท่านั้น")
            return
    if new_emoji:
        product['emoji'] = new_emoji
    if new_category:
        product['category'] = new_category
    
    products[product_idx] = product
    save_products(products)
    await ctx.send(f"✅ แก้ไขสินค้า {product['emoji']} {product['name']} เรียบร้อยแล้ว")

@bot.tree.command(name="แก้ไขสินค้า", description="แก้ไขสินค้า (สำหรับแอดมินเท่านั้น)")
@commands.has_permissions(administrator=True)
async def edit_product_slash(
    interaction: discord.Interaction, 
    ชื่อ: str, 
    ชื่อใหม่: str = None, 
    ราคาใหม่: int = None, 
    อีโมจิใหม่: str = None, 
    หมวดใหม่: str = None
):
    """Slash command to edit a product"""
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ คุณไม่มีสิทธิ์ใช้คำสั่งนี้", ephemeral=True)
        return
        
    products = load_products()
    
    # Find the product
    product_idx = next((i for i, p in enumerate(products) if p['name'] == ชื่อ), None)
    if product_idx is None:
        await interaction.response.send_message(f"❌ ไม่พบสินค้า '{ชื่อ}'", ephemeral=True)
        return
    
    product = products[product_idx]
    
    # Update the product
    if ชื่อใหม่:
        product['name'] = ชื่อใหม่
    if ราคาใหม่ is not None:
        product['price'] = ราคาใหม่
    if อีโมจิใหม่:
        product['emoji'] = อีโมจิใหม่
    if หมวดใหม่:
        product['category'] = หมวดใหม่
    
    products[product_idx] = product
    save_products(products)
    await interaction.response.send_message(f"✅ แก้ไขสินค้า {product['emoji']} {product['name']} เรียบร้อยแล้ว")

@bot.command(name="ประวัติ")
@commands.has_permissions(administrator=True)
async def view_history(ctx, limit: int = 5):
    """View purchase history (admin only)"""
    history = load_history()
    
    if not history:
        await ctx.send("❌ ไม่มีประวัติการซื้อ")
        return
    
    # Sort by timestamp, newest first
    history.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
    
    # Limit the number of entries
    history = history[:limit]
    
    # Create embed
    embed = discord.Embed(title="📊 ประวัติการซื้อล่าสุด", color=0xf1c40f)
    
    for i, entry in enumerate(history):
        # Format timestamp
        timestamp = entry.get('timestamp', '')
        if timestamp:
            try:
                dt = datetime.fromisoformat(timestamp)
                formatted_time = dt.strftime('%d/%m/%Y %H:%M')
            except ValueError:
                formatted_time = timestamp
        else:
            formatted_time = "ไม่ระบุเวลา"
        
        # Format items
        items_text = ""
        for item in entry.get('items', []):
            items_text += f"• {item.get('name', 'ไม่ระบุ')} x{item.get('qty', 1)} ({item.get('price', 0)}฿)\n"
        
        # Add field
        embed.add_field(
            name=f"{i+1}. ผู้ซื้อ: {entry.get('user', 'ไม่ระบุ')} - {formatted_time}",
            value=f"{items_text}**ยอดรวม:** {entry.get('total', 0)}฿",
            inline=False
        )
    
    await ctx.send(embed=embed)

@bot.tree.command(name="ประวัติ", description="ดูประวัติการซื้อ (สำหรับแอดมินเท่านั้น)")
@commands.has_permissions(administrator=True)
async def view_history_slash(interaction: discord.Interaction, จำนวน: int = 5):
    """Slash command to view purchase history"""
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ คุณไม่มีสิทธิ์ใช้คำสั่งนี้", ephemeral=True)
        return
        
    history = load_history()
    
    if not history:
        await interaction.response.send_message("❌ ไม่มีประวัติการซื้อ")
        return
    
    # Sort by timestamp, newest first
    history.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
    
    # Limit the number of entries
    history = history[:จำนวน]
    
    # Create embed
    embed = discord.Embed(title="📊 ประวัติการซื้อล่าสุด", color=0xf1c40f)
    
    for i, entry in enumerate(history):
        # Format timestamp
        timestamp = entry.get('timestamp', '')
        if timestamp:
            try:
                dt = datetime.fromisoformat(timestamp)
                formatted_time = dt.strftime('%d/%m/%Y %H:%M')
            except ValueError:
                formatted_time = timestamp
        else:
            formatted_time = "ไม่ระบุเวลา"
        
        # Format items
        items_text = ""
        for item in entry.get('items', []):
            items_text += f"• {item.get('name', 'ไม่ระบุ')} x{item.get('qty', 1)} ({item.get('price', 0)}฿)\n"
        
        # Add field
        embed.add_field(
            name=f"{i+1}. ผู้ซื้อ: {entry.get('user', 'ไม่ระบุ')} - {formatted_time}",
            value=f"{items_text}**ยอดรวม:** {entry.get('total', 0)}฿",
            inline=False
        )
    
    await interaction.response.send_message(embed=embed)

@bot.command(name="ช่วยเหลือ")
async def help_command(ctx):
    """Display help information"""
    embed = discord.Embed(title="🛠️ คำสั่งทั้งหมด", color=0x9b59b6)
    
    # Commands for all users
    embed.add_field(
        name="📌 คำสั่งทั่วไป",
        value=(
            "**!ร้าน [หมวด]** - เปิดร้านค้าเพื่อซื้อสินค้า (หมวดเป็นตัวเลือก)\n"
            "**!สินค้าทั้งหมด [หมวด]** - แสดงรายการสินค้าทั้งหมด (หมวดเป็นตัวเลือก)\n"
            "**!ช่วยเหลือ** - แสดงข้อมูลช่วยเหลือ"
        ),
        inline=False
    )
    
    # Category shortcuts
    embed.add_field(
        name="🏷️ คำสั่งลัดหมวดหมู่",
        value=(
            "**!เงิน** หรือ **!money** - เปิดร้านค้าหมวดเงิน\n"
            "**!อาวุธ** หรือ **!weapon** - เปิดร้านค้าหมวดอาวุธ\n"
            "**!ไอเทม** หรือ **!item** - เปิดร้านค้าหมวดไอเทม\n"
            "**!รถ** หรือ **!car** - เปิดร้านค้าหมวดรถ\n"
            "**!แฟชั่น** หรือ **!fashion** - เปิดร้านค้าหมวดแฟชั่น\n"
            "**!เช่ารถ** - เปิดร้านค้าหมวดเช่ารถ"
        ),
        inline=False
    )
    
    # Admin commands
    embed.add_field(
        name="👑 คำสั่งสำหรับแอดมิน",
        value=(
            "**!เพิ่มสินค้า [ชื่อ] [ราคา] [อีโมจิ] [หมวด]** - เพิ่มสินค้าใหม่ (หมวดเป็นตัวเลือก ค่าเริ่มต้นคือ 'item')\n"
            "**!ลบสินค้า [ชื่อ]** - ลบสินค้า\n"
            "**!แก้ไขสินค้า [ชื่อ] [ชื่อใหม่] [ราคาใหม่] [อีโมจิใหม่] [หมวดใหม่]** - แก้ไขสินค้า (พารามิเตอร์ทั้งหมดยกเว้นชื่อเป็นตัวเลือก)\n"
            "**!ประวัติ [จำนวน]** - ดูประวัติการซื้อล่าสุด (จำนวนเป็นตัวเลือก ค่าเริ่มต้นคือ 5)"
        ),
        inline=False
    )
    
    embed.set_footer(text="คุณยังสามารถใช้คำสั่ง / ได้อีกด้วย เช่น /ร้าน, /เพิ่มสินค้า เป็นต้น")
    
    await ctx.send(embed=embed)

@bot.tree.command(name="ช่วยเหลือ", description="แสดงข้อมูลช่วยเหลือ")
async def help_slash(interaction: discord.Interaction):
    """Slash command to display help information"""
    embed = discord.Embed(title="🛠️ คำสั่งทั้งหมด", color=0x9b59b6)
    
    # Commands for all users
    embed.add_field(
        name="📌 คำสั่งทั่วไป",
        value=(
            "**/ร้าน [หมวด]** - เปิดร้านค้าเพื่อซื้อสินค้า (หมวดเป็นตัวเลือก)\n"
            "**/สินค้าทั้งหมด [หมวด]** - แสดงรายการสินค้าทั้งหมด (หมวดเป็นตัวเลือก)\n"
            "**/ช่วยเหลือ** - แสดงข้อมูลช่วยเหลือ"
        ),
        inline=False
    )
    
    # Admin commands
    embed.add_field(
        name="👑 คำสั่งสำหรับแอดมิน",
        value=(
            "**/เพิ่มสินค้า [ชื่อ] [ราคา] [อีโมจิ] [หมวด]** - เพิ่มสินค้าใหม่ (หมวดเป็นตัวเลือก ค่าเริ่มต้นคือ 'item')\n"
            "**/ลบสินค้า [ชื่อ]** - ลบสินค้า\n"
            "**/แก้ไขสินค้า [ชื่อ] [ชื่อใหม่] [ราคาใหม่] [อีโมจิใหม่] [หมวดใหม่]** - แก้ไขสินค้า (พารามิเตอร์ทั้งหมดยกเว้นชื่อเป็นตัวเลือก)\n"
            "**/ประวัติ [จำนวน]** - ดูประวัติการซื้อล่าสุด (จำนวนเป็นตัวเลือก ค่าเริ่มต้นคือ 5)"
        ),
        inline=False
    )
    
    embed.set_footer(text="คุณยังสามารถใช้คำสั่ง ! ได้อีกด้วย เช่น !ร้าน, !เพิ่มสินค้า เป็นต้น")
    
    await interaction.response.send_message(embed=embed)

@bot.event
async def on_command_error(ctx, error):
    """Global error handler for prefix commands"""
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ คุณไม่มีสิทธิ์ใช้คำสั่งนี้")
    elif isinstance(error, commands.CommandNotFound):
        pass  # Ignore command not found errors
    else:
        logger.error(f"Command error: {error}")
        await ctx.send(f"❌ เกิดข้อผิดพลาด: {error}")

# Run the bot
def main():
    """Main function to run the bot"""
    token = os.environ.get("DISCORD_BOT_TOKEN")
    if not token:
        logger.error("No Discord bot token found. Set the DISCORD_BOT_TOKEN environment variable.")
        return

    try:
        # Start the web server to keep the bot alive
        keep_alive()
        # Start the bot
        bot.run(token)
    except Exception as e:
        logger.error(f"Error running bot: {e}")

if __name__ == "__main__":
    main()
