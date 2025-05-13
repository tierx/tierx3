import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput
import json
import os
from datetime import datetime
from pathlib import Path
import re
from myserver import server_on

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
        print(f"Products file not found at {PRODUCTS_FILE}")
        return []
    except json.JSONDecodeError:
        print(f"Invalid JSON in products file at {PRODUCTS_FILE}")
        return []

def save_products(products):
    """Save product data to the JSON file"""
    with open(PRODUCTS_FILE, "w", encoding="utf-8") as f:
        json.dump(products, f, ensure_ascii=False, indent=2)

def log_purchase(user, items, total_price):
    """Log purchase history to the JSON file"""
    # Create the history file if it doesn't exist
    if not HISTORY_FILE.exists():
        HISTORY_FILE.touch()
        
    with open(HISTORY_FILE, "a", encoding="utf-8") as f:
        data = {
            "user": str(user),
            "items": items,
            "total": total_price,
            "timestamp": datetime.now().isoformat()
        }
        f.write(json.dumps(data, ensure_ascii=False) + "\n")

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
            await interaction.response.send_message(f"❌ เกิดข้อผิดพลาด: {str(e)}", ephemeral=True)

@bot.event
async def on_ready():
    """Event triggered when the bot is ready"""
    print(f"Bot is ready! Logged in as {bot.user}")
    
    # Create history file if it doesn't exist
    if not HISTORY_FILE.exists():
        HISTORY_FILE.touch()
        print(f"Created history file at {HISTORY_FILE}")
    
    # Register slash commands
    try:
        print("Registering slash commands...")
        # Shop Commands
        await bot.tree.sync()
        print("Slash commands registered successfully!")
    except Exception as e:
        print(f"Error registering slash commands: {e}")

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
async def shop(ctx, หมวด: str = None):
    """Command to open the shop"""
    # Check if the category is valid
    valid_categories = ["money", "weapon", "item", "car", "fashion", "เช่ารถ"]
    
    if หมวด and หมวด not in valid_categories:
        categories_str = ", ".join([f"`{cat}`" for cat in valid_categories])
        await ctx.send(f"❌ หมวดหมู่ไม่ถูกต้อง หมวดหมู่ที่มี: {categories_str}")
        return
    
    view = ShopView(category=หมวด)
    
    # If no products in this category
    if len(view.products) == 0:
        await ctx.send(f"❌ ไม่มีสินค้าในหมวด `{หมวด}`")
        return
    
    title = "เลือกสินค้าที่คุณต้องการ:"
    if หมวด:
        title = f"🛍️ หมวด `{หมวด}` - เลือกสินค้าที่คุณต้องการ:"
    
    await ctx.send(title, view=view)

@bot.command(name="เพิ่มสินค้า")
@commands.has_permissions(administrator=True)
async def add_product(ctx, ชื่อ: str, ราคา: int, อีโมจิ: str, หมวด: str = "item"):
    """Command to add a new product (Admin only)"""
    try:
        # Check if the category is valid
        valid_categories = ["money", "weapon", "item", "car", "fashion", "เช่ารถ"]
        if หมวด not in valid_categories:
            categories_str = ", ".join([f"`{cat}`" for cat in valid_categories])
            await ctx.send(f"❌ หมวดหมู่ไม่ถูกต้อง หมวดหมู่ที่มี: {categories_str}")
            return
        
        products = load_products()
        # Check if product already exists
        for product in products:
            if product["name"] == ชื่อ:
                await ctx.send(f"❌ สินค้า '{ชื่อ}' มีอยู่แล้ว")
                return
                
        products.append({"name": ชื่อ, "price": ราคา, "emoji": อีโมจิ, "category": หมวด})
        save_products(products)
        await ctx.send(f"✅ เพิ่มสินค้า: {อีโมจิ} {ชื่อ} - {ราคา}฿ (หมวด: {หมวด})")
    except Exception as e:
        await ctx.send(f"❌ เกิดข้อผิดพลาด: {str(e)}")

@bot.command(name="ลบสินค้า")
@commands.has_permissions(administrator=True)
async def remove_product(ctx, ชื่อ: str):
    """Command to remove a product (Admin only)"""
    try:
        products = load_products()
        original_count = len(products)
        
        # Find product to show category before deletion
        product_to_delete = next((p for p in products if p["name"] == ชื่อ), None)
        if not product_to_delete:
            await ctx.send(f"❌ ไม่พบสินค้า '{ชื่อ}'")
            return
        
        # Remove the product
        products = [p for p in products if p["name"] != ชื่อ]
        save_products(products)
        
        category = product_to_delete.get("category", "ไม่ระบุหมวด")
        await ctx.send(f"🗑️ ลบสินค้า '{ชื่อ}' จากหมวด '{category}' เรียบร้อย")
    except Exception as e:
        await ctx.send(f"❌ เกิดข้อผิดพลาด: {str(e)}")

@bot.command(name="แก้ไขสินค้า")
@commands.has_permissions(administrator=True)
async def edit_product(ctx, ชื่อ: str, ชื่อใหม่: str = None, ราคาใหม่: int = None, อีโมจิใหม่: str = None, หมวดใหม่: str = None):
    """Command to edit a product (Admin only)"""
    try:
        # Check if the new category is valid
        valid_categories = ["money", "weapon", "item", "car", "fashion", "เช่ารถ"]
        if หมวดใหม่ and หมวดใหม่ not in valid_categories:
            categories_str = ", ".join([f"`{cat}`" for cat in valid_categories])
            await ctx.send(f"❌ หมวดหมู่ไม่ถูกต้อง หมวดหมู่ที่มี: {categories_str}")
            return
        
        products = load_products()
        
        # Find the product
        found = False
        for product in products:
            if product["name"] == ชื่อ:
                found = True
                
                # Update product details if provided
                if ชื่อใหม่:
                    product["name"] = ชื่อใหม่
                if ราคาใหม่ is not None:
                    product["price"] = ราคาใหม่
                if อีโมจิใหม่:
                    product["emoji"] = อีโมจิใหม่
                if หมวดใหม่:
                    product["category"] = หมวดใหม่
                
                break
        
        if not found:
            await ctx.send(f"❌ ไม่พบสินค้า '{ชื่อ}'")
            return
            
        save_products(products)
        
        product_name = ชื่อใหม่ if ชื่อใหม่ else ชื่อ
        await ctx.send(f"✏️ แก้ไขสินค้า '{ชื่อ}' เรียบร้อย")
        
        # Show updated product details
        product = next((p for p in products if p["name"] == product_name), None)
        if product:
            embed = discord.Embed(title="✅ ข้อมูลสินค้าที่อัปเดต", color=0x00ff00)
            embed.add_field(name="ชื่อ", value=product["name"], inline=True)
            embed.add_field(name="ราคา", value=f"{product['price']}฿", inline=True)
            embed.add_field(name="อีโมจิ", value=product["emoji"], inline=True)
            embed.add_field(name="หมวดหมู่", value=product.get("category", "ไม่ระบุหมวด"), inline=True)
            await ctx.send(embed=embed)
            
    except Exception as e:
        await ctx.send(f"❌ เกิดข้อผิดพลาด: {str(e)}")

@bot.command(name="สินค้าทั้งหมด")
async def list_products(ctx, หมวด: str = None):
    """Command to list all products"""
    products = load_products()
    if not products:
        await ctx.send("❌ ไม่มีสินค้าในร้าน")
        return
    
    # Check if category is valid
    valid_categories = ["money", "weapon", "item", "car", "fashion", "เช่ารถ"]
    if หมวด and หมวด not in valid_categories:
        categories_str = ", ".join([f"`{cat}`" for cat in valid_categories])
        await ctx.send(f"❌ หมวดหมู่ไม่ถูกต้อง หมวดหมู่ที่มี: {categories_str}")
        return
    
    # Filter products by category if specified
    if หมวด:
        filtered_products = [p for p in products if p.get('category', '') == หมวด]
        if not filtered_products:
            await ctx.send(f"❌ ไม่มีสินค้าในหมวด `{หมวด}`")
            return
        products = filtered_products
        embed_title = f"📋 รายการสินค้าในหมวด '{หมวด}'"
    else:
        # Group products by category
        categories = {}
        for product in products:
            category = product.get('category', 'ไม่ระบุหมวด')
            if category not in categories:
                categories[category] = []
            categories[category].append(product)
        
        embed_title = "📋 รายการสินค้าทั้งหมด (แยกตามหมวด)"
        embed = discord.Embed(title=embed_title, color=0x3498db)
        
        # Add category sections
        for category, category_products in categories.items():
            product_list = []
            for product in category_products:
                product_list.append(f"{product['emoji']} {product['name']} - {product['price']}฿")
            
            # Join products with newlines
            value = "\n".join(product_list) if product_list else "ไม่มีสินค้า"
            
            # Add field for this category
            embed.add_field(
                name=f"🏷️ {category.upper()}",
                value=value,
                inline=False
            )
        
        await ctx.send(embed=embed)
        return
    
    # Show products for a specific category
    embed = discord.Embed(title=embed_title, color=0x3498db)
    
    for product in products:
        embed.add_field(
            name=f"{product['emoji']} {product['name']}",
            value=f"ราคา: {product['price']}฿",
            inline=True
        )
    
    await ctx.send(embed=embed)

@bot.command(name="ประวัติ")
@commands.has_permissions(administrator=True)
async def history(ctx, จำนวน: int = 5):
    """Command to view purchase history (Admin only)"""
    try:
        if not HISTORY_FILE.exists() or HISTORY_FILE.stat().st_size == 0:
            await ctx.send("❌ ยังไม่มีประวัติการซื้อ")
            return
            
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()
            
        if not lines:
            await ctx.send("❌ ยังไม่มีประวัติการซื้อ")
            return
            
        # Get the last N entries
        entries = lines[-จำนวน:] if จำนวน > 0 else lines
            
        embed = discord.Embed(title="📜 ประวัติการซื้อ", color=0x00ff00)
        for line in entries:
            try:
                d = json.loads(line)
                dt = datetime.fromisoformat(d['timestamp'])
                formatted_time = dt.strftime("%d/%m/%Y %H:%M")
                summary = ", ".join([f"{x['name']} x{x['qty']}" for x in d['items']])
                embed.add_field(
                    name=f"👤 {d['user']} ({formatted_time})",
                    value=f"{summary} = {d['total']}฿",
                    inline=False
                )
            except (json.JSONDecodeError, KeyError) as e:
                continue
                
        await ctx.send(embed=embed)
    except Exception as e:
        await ctx.send(f"❌ เกิดข้อผิดพลาด: {str(e)}")

@bot.command(name="ช่วยเหลือ")
async def help_command(ctx):
    """Command to display help information"""
    embed = discord.Embed(title="📚 คำสั่งทั้งหมด", color=0xffa500)
    
    # General commands
    embed.add_field(
        name="!ร้าน หรือ /ร้าน",
        value="เปิดร้านค้าเพื่อซื้อสินค้า",
        inline=False
    )
    embed.add_field(
        name="!ร้าน [หมวด] หรือ /ร้าน [หมวด]",
        value="เปิดร้านค้าโดยระบุหมวดหมู่ (เงิน, อาวุธ, ไอเทม, รถยนต์, แฟชั่น, เช่ารถ)",
        inline=False
    )
    
    # Category shortcut commands
    embed.add_field(
        name="!money (!เงิน), !weapon (!อาวุธ), !item (!ไอเทม)",
        value="คำสั่งลัดเปิดร้านค้าตามหมวดหมู่",
        inline=False
    )
    embed.add_field(
        name="!car (!รถ), !fashion (!แฟชั่น), !เช่ารถ",
        value="คำสั่งลัดเปิดร้านค้าตามหมวดหมู่ (ต่อ)",
        inline=False
    )
    
    embed.add_field(
        name="!สินค้าทั้งหมด หรือ /สินค้าทั้งหมด",
        value="แสดงรายการสินค้าทั้งหมด",
        inline=False
    )
    embed.add_field(
        name="!สินค้าทั้งหมด [หมวด] หรือ /สินค้าทั้งหมด [หมวด]",
        value="แสดงรายการสินค้าในหมวดที่ระบุ",
        inline=False
    )
    
    # Admin commands
    embed.add_field(
        name="👑 คำสั่งสำหรับแอดมิน",
        value="คำสั่งต่อไปนี้ใช้ได้เฉพาะผู้ที่มีสิทธิ์ผู้ดูแล (Administrator)",
        inline=False
    )
    embed.add_field(
        name="!เพิ่มสินค้า [ชื่อ] [ราคา] [อีโมจิ]\nหรือ /เพิ่มสินค้า",
        value="เพิ่มสินค้าใหม่เข้าร้าน",
        inline=True
    )
    embed.add_field(
        name="!ลบสินค้า [ชื่อ]\nหรือ /ลบสินค้า",
        value="ลบสินค้าออกจากร้าน",
        inline=True
    )
    embed.add_field(
        name="!แก้ไขสินค้า [ชื่อ] [ชื่อใหม่] [ราคาใหม่] [อีโมจิใหม่]\nหรือ /แก้ไขสินค้า",
        value="แก้ไขข้อมูลสินค้า (สามารถระบุเฉพาะข้อมูลที่ต้องการแก้ไข)",
        inline=True
    )
    embed.add_field(
        name="!ประวัติ [จำนวน]\nหรือ /ประวัติ",
        value="ดูประวัติการซื้อล่าสุดตามจำนวนที่ระบุ (ค่าเริ่มต้นคือ 5)",
        inline=True
    )
    
    await ctx.send(embed=embed)

@bot.event
async def on_command_error(ctx, error):
    """Error handler for bot commands"""
    if isinstance(error, commands.CommandNotFound):
        return
    elif isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ คุณไม่มีสิทธิ์ใช้คำสั่งนี้ ต้องการสิทธิ์ผู้ดูแล (Administrator)")
    elif isinstance(error, commands.MissingRole):
        await ctx.send("❌ คุณไม่มีสิทธิ์ใช้คำสั่งนี้")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"❌ คำสั่งไม่ถูกต้อง: {str(error)}")
    elif isinstance(error, commands.BadArgument):
        await ctx.send("❌ รูปแบบคำสั่งไม่ถูกต้อง กรุณาตรวจสอบว่าข้อมูลที่ใส่ถูกต้อง")
    else:
        await ctx.send(f"❌ เกิดข้อผิดพลาด: {str(error)}")
        print(f"Command error: {error}")

# Get token from environment variables with fallback to a default value (for testing)
TOKEN = os.getenv("DISCORD_BOT_TOKEN", "")

if not TOKEN:
    print("❌ ERROR: Discord bot token not provided. Please set the DISCORD_BOT_TOKEN environment variable.")
    exit(1)

# Define slash commands
@bot.tree.command(name="ร้าน", description="เปิดร้านค้าเพื่อซื้อสินค้า")
@discord.app_commands.describe(หมวด="หมวดหมู่สินค้าที่ต้องการดู")
@discord.app_commands.choices(หมวด=[
    discord.app_commands.Choice(name="เงิน", value="money"),
    discord.app_commands.Choice(name="อาวุธ", value="weapon"),
    discord.app_commands.Choice(name="ไอเทม", value="item"),
    discord.app_commands.Choice(name="รถยนต์", value="car"),
    discord.app_commands.Choice(name="แฟชั่น", value="fashion"),
    discord.app_commands.Choice(name="เช่ารถ", value="เช่ารถ")
])
async def shop_slash(interaction: discord.Interaction, หมวด: str = None):
    """Slash command to open the shop"""
    view = ShopView(category=หมวด)
    
    # If no products in this category
    if len(view.products) == 0:
        await interaction.response.send_message(f"❌ ไม่มีสินค้าในหมวด `{หมวด}`")
        return
    
    title = "เลือกสินค้าที่คุณต้องการ:"
    if หมวด:
        title = f"🛍️ หมวด `{หมวด}` - เลือกสินค้าที่คุณต้องการ:"
    
    await interaction.response.send_message(title, view=view)

@bot.tree.command(name="สินค้าทั้งหมด", description="แสดงรายการสินค้าทั้งหมด")
@discord.app_commands.describe(หมวด="หมวดหมู่สินค้าที่ต้องการดู")
@discord.app_commands.choices(หมวด=[
    discord.app_commands.Choice(name="เงิน", value="money"),
    discord.app_commands.Choice(name="อาวุธ", value="weapon"),
    discord.app_commands.Choice(name="ไอเทม", value="item"),
    discord.app_commands.Choice(name="รถยนต์", value="car"),
    discord.app_commands.Choice(name="แฟชั่น", value="fashion"),
    discord.app_commands.Choice(name="เช่ารถ", value="เช่ารถ")
])
async def list_products_slash(interaction: discord.Interaction, หมวด: str = None):
    """Slash command to list all products"""
    products = load_products()
    if not products:
        await interaction.response.send_message("❌ ไม่มีสินค้าในร้าน")
        return
        
    embed = discord.Embed(title="📋 รายการสินค้าทั้งหมด", color=0x3498db)
    
    for product in products:
        embed.add_field(
            name=f"{product['emoji']} {product['name']}",
            value=f"ราคา: {product['price']}฿",
            inline=True
        )
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="เพิ่มสินค้า", description="เพิ่มสินค้าใหม่เข้าร้าน (Admin only)")
@discord.app_commands.describe(
    ชื่อ="ชื่อของสินค้า",
    ราคา="ราคาของสินค้า (ตัวเลข)",
    อีโมจิ="อีโมจิที่แสดงหน้าสินค้า (สามารถใช้อีโมจิของเซิร์ฟเวอร์ได้ เช่น :emoji_name:)",
    หมวด="หมวดหมู่ของสินค้า (เลือกได้)"
)
@discord.app_commands.choices(หมวด=[
    discord.app_commands.Choice(name="เงิน", value="money"),
    discord.app_commands.Choice(name="อาวุธ", value="weapon"),
    discord.app_commands.Choice(name="ไอเทม", value="item"),
    discord.app_commands.Choice(name="รถยนต์", value="car"),
    discord.app_commands.Choice(name="แฟชั่น", value="fashion"),
    discord.app_commands.Choice(name="เช่ารถ", value="เช่ารถ")
])
async def add_product_slash(interaction: discord.Interaction, ชื่อ: str, ราคา: int, อีโมจิ: str, หมวด: str = "item"):
    """Slash command to add a new product (Admin only)"""
    # Check if user has Administrator permissions
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ คุณไม่มีสิทธิ์ใช้คำสั่งนี้ ต้องการสิทธิ์ผู้ดูแล (Administrator)", ephemeral=True)
        return
        
    try:
        # Parse custom emoji if provided in <:name:id> format
        emoji_to_use = อีโมจิ
        if อีโมจิ.startswith("<") and อีโมจิ.endswith(">"):
            # Already in proper format, use as is
            pass
        elif อีโมจิ.startswith(":") and อีโมจิ.endswith(":"):
            # Convert :emoji_name: to actual emoji
            emoji_name = อีโมจิ.strip(":")
            # Try to find the emoji in the server
            found_emoji = discord.utils.get(interaction.guild.emojis, name=emoji_name)
            if found_emoji:
                emoji_to_use = str(found_emoji)
            else:
                await interaction.response.send_message(f"❌ ไม่พบอีโมจิ '{อีโมจิ}' ในเซิร์ฟเวอร์นี้", ephemeral=True)
                return
        
        products = load_products()
        # Check if product already exists
        for product in products:
            if product["name"] == ชื่อ:
                await interaction.response.send_message(f"❌ สินค้า '{ชื่อ}' มีอยู่แล้ว", ephemeral=True)
                return
                
        products.append({"name": ชื่อ, "price": ราคา, "emoji": emoji_to_use, "category": หมวด})
        save_products(products)
        await interaction.response.send_message(f"✅ เพิ่มสินค้า: {emoji_to_use} {ชื่อ} - {ราคา}฿ (หมวด: {หมวด})")
    except Exception as e:
        await interaction.response.send_message(f"❌ เกิดข้อผิดพลาด: {str(e)}", ephemeral=True)

@bot.tree.command(name="ลบสินค้า", description="ลบสินค้าออกจากร้าน (Admin only)")
@discord.app_commands.describe(ชื่อ="ชื่อของสินค้าที่ต้องการลบ")
async def remove_product_slash(interaction: discord.Interaction, ชื่อ: str):
    """Slash command to remove a product (Admin only)"""
    # Check if user has Administrator permissions
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ คุณไม่มีสิทธิ์ใช้คำสั่งนี้ ต้องการสิทธิ์ผู้ดูแล (Administrator)", ephemeral=True)
        return
        
    try:
        products = load_products()
        original_count = len(products)
        
        # Find product to show category before deletion
        product_to_delete = next((p for p in products if p["name"] == ชื่อ), None)
        if not product_to_delete:
            await interaction.response.send_message(f"❌ ไม่พบสินค้า '{ชื่อ}'", ephemeral=True)
            return
        
        # Remove the product
        products = [p for p in products if p["name"] != ชื่อ]
        save_products(products)
        
        category = product_to_delete.get("category", "ไม่ระบุหมวด")
        await interaction.response.send_message(f"🗑️ ลบสินค้า '{ชื่อ}' จากหมวด '{category}' เรียบร้อย")
    except Exception as e:
        await interaction.response.send_message(f"❌ เกิดข้อผิดพลาด: {str(e)}", ephemeral=True)

@bot.tree.command(name="แก้ไขสินค้า", description="แก้ไขข้อมูลสินค้า (Admin only)")
@discord.app_commands.describe(
    ชื่อ="ชื่อของสินค้าที่ต้องการแก้ไข",
    ชื่อใหม่="ชื่อใหม่ของสินค้า (ไม่ระบุหากไม่ต้องการเปลี่ยน)",
    ราคาใหม่="ราคาใหม่ของสินค้า (ไม่ระบุหากไม่ต้องการเปลี่ยน)",
    อีโมจิใหม่="อีโมจิใหม่ของสินค้า (ไม่ระบุหากไม่ต้องการเปลี่ยน)",
    หมวดใหม่="หมวดหมู่ใหม่ของสินค้า (ไม่ระบุหากไม่ต้องการเปลี่ยน)"
)
@discord.app_commands.choices(หมวดใหม่=[
    discord.app_commands.Choice(name="เงิน", value="money"),
    discord.app_commands.Choice(name="อาวุธ", value="weapon"),
    discord.app_commands.Choice(name="ไอเทม", value="item"),
    discord.app_commands.Choice(name="รถยนต์", value="car"),
    discord.app_commands.Choice(name="แฟชั่น", value="fashion"),
    discord.app_commands.Choice(name="เช่ารถ", value="เช่ารถ")
])
async def edit_product_slash(interaction: discord.Interaction, ชื่อ: str, ชื่อใหม่: str = None, ราคาใหม่: int = None, อีโมจิใหม่: str = None, หมวดใหม่: str = None):
    """Slash command to edit a product (Admin only)"""
    # Check if user has Administrator permissions
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ คุณไม่มีสิทธิ์ใช้คำสั่งนี้ ต้องการสิทธิ์ผู้ดูแล (Administrator)", ephemeral=True)
        return
        
    # Check if the new category is valid if provided
    valid_categories = ["money", "weapon", "item", "car", "fashion", "เช่ารถ"]
    if หมวดใหม่ and หมวดใหม่ not in valid_categories:
        categories_str = ", ".join([f"`{cat}`" for cat in valid_categories])
        await interaction.response.send_message(f"❌ หมวดหมู่ไม่ถูกต้อง หมวดหมู่ที่มี: {categories_str}", ephemeral=True)
        return
        
    try:
        products = load_products()
        
        # Find the product
        found = False
        for product in products:
            if product["name"] == ชื่อ:
                found = True
                
                # Update product details if provided
                if ชื่อใหม่:
                    product["name"] = ชื่อใหม่
                if ราคาใหม่ is not None:
                    product["price"] = ราคาใหม่
                if อีโมจิใหม่:
                    product["emoji"] = อีโมจิใหม่
                if หมวดใหม่:
                    product["category"] = หมวดใหม่
                
                break
        
        if not found:
            await interaction.response.send_message(f"❌ ไม่พบสินค้า '{ชื่อ}'", ephemeral=True)
            return
            
        save_products(products)
        
        product_name = ชื่อใหม่ if ชื่อใหม่ else ชื่อ
        
        # Show updated product details
        product = next((p for p in products if p["name"] == product_name), None)
        if product:
            embed = discord.Embed(title="✅ ข้อมูลสินค้าที่อัปเดต", color=0x00ff00)
            embed.add_field(name="ชื่อ", value=product["name"], inline=True)
            embed.add_field(name="ราคา", value=f"{product['price']}฿", inline=True)
            embed.add_field(name="อีโมจิ", value=product["emoji"], inline=True)
            
            # Add category field if present
            if "category" in product:
                category_name = product["category"]
                category_display = {
                    "money": "เงิน",
                    "weapon": "อาวุธ",
                    "item": "ไอเทม",
                    "car": "รถยนต์",
                    "fashion": "แฟชั่น",
                    "เช่ารถ": "เช่ารถ"
                }.get(category_name, category_name)
                embed.add_field(name="หมวดหมู่", value=category_display, inline=True)
                
            await interaction.response.send_message(embed=embed)
            
    except Exception as e:
        await interaction.response.send_message(f"❌ เกิดข้อผิดพลาด: {str(e)}", ephemeral=True)

@bot.tree.command(name="ประวัติ", description="ดูประวัติการซื้อล่าสุด (Admin only)")
@discord.app_commands.describe(จำนวน="จำนวนรายการที่ต้องการดู (ค่าเริ่มต้นคือ 5)")
async def history_slash(interaction: discord.Interaction, จำนวน: int = 5):
    """Slash command to view purchase history (Admin only)"""
    # Check if user has Administrator permissions
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ คุณไม่มีสิทธิ์ใช้คำสั่งนี้ ต้องการสิทธิ์ผู้ดูแล (Administrator)", ephemeral=True)
        return
        
    try:
        if not HISTORY_FILE.exists() or HISTORY_FILE.stat().st_size == 0:
            await interaction.response.send_message("❌ ยังไม่มีประวัติการซื้อ", ephemeral=True)
            return
            
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()
            
        if not lines:
            await interaction.response.send_message("❌ ยังไม่มีประวัติการซื้อ", ephemeral=True)
            return
            
        # Get the last N entries
        entries = lines[-จำนวน:] if จำนวน > 0 else lines
            
        embed = discord.Embed(title="📜 ประวัติการซื้อ", color=0x00ff00)
        for line in entries:
            try:
                d = json.loads(line)
                dt = datetime.fromisoformat(d['timestamp'])
                formatted_time = dt.strftime("%d/%m/%Y %H:%M")
                summary = ", ".join([f"{x['name']} x{x['qty']}" for x in d['items']])
                embed.add_field(
                    name=f"👤 {d['user']} ({formatted_time})",
                    value=f"{summary} = {d['total']}฿",
                    inline=False
                )
            except (json.JSONDecodeError, KeyError) as e:
                continue
                
        await interaction.response.send_message(embed=embed)
    except Exception as e:
        await interaction.response.send_message(f"❌ เกิดข้อผิดพลาด: {str(e)}", ephemeral=True)

@bot.tree.command(name="ช่วยเหลือ", description="แสดงข้อมูลคำสั่งทั้งหมด")
async def help_slash(interaction: discord.Interaction):
    """Slash command to display help information"""
    embed = discord.Embed(title="📚 คำสั่งทั้งหมด", color=0xffa500)
    
    # General commands
    embed.add_field(
        name="/ร้าน หรือ !ร้าน",
        value="เปิดร้านค้าเพื่อซื้อสินค้า",
        inline=False
    )
    embed.add_field(
        name="/ร้าน [หมวด] หรือ !ร้าน [หมวด]",
        value="เปิดร้านค้าโดยระบุหมวดหมู่ (เงิน, อาวุธ, ไอเทม, รถยนต์, แฟชั่น, เช่ารถ)",
        inline=False
    )
    
    # Category shortcut commands
    embed.add_field(
        name="!money (!เงิน), !weapon (!อาวุธ), !item (!ไอเทม)",
        value="คำสั่งลัดเปิดร้านค้าตามหมวดหมู่",
        inline=False
    )
    embed.add_field(
        name="!car (!รถ), !fashion (!แฟชั่น), !เช่ารถ",
        value="คำสั่งลัดเปิดร้านค้าตามหมวดหมู่ (ต่อ)",
        inline=False
    )
    
    embed.add_field(
        name="/สินค้าทั้งหมด หรือ !สินค้าทั้งหมด",
        value="แสดงรายการสินค้าทั้งหมด",
        inline=False
    )
    embed.add_field(
        name="/สินค้าทั้งหมด [หมวด] หรือ !สินค้าทั้งหมด [หมวด]",
        value="แสดงรายการสินค้าในหมวดที่ระบุ",
        inline=False
    )
    
    # Admin commands
    embed.add_field(
        name="👑 คำสั่งสำหรับแอดมิน",
        value="คำสั่งต่อไปนี้ใช้ได้เฉพาะผู้ที่มีสิทธิ์ผู้ดูแล (Administrator)",
        inline=False
    )
    embed.add_field(
        name="/เพิ่มสินค้า หรือ !เพิ่มสินค้า",
        value="เพิ่มสินค้าใหม่เข้าร้าน",
        inline=True
    )
    embed.add_field(
        name="/ลบสินค้า หรือ !ลบสินค้า",
        value="ลบสินค้าออกจากร้าน",
        inline=True
    )
    embed.add_field(
        name="/แก้ไขสินค้า หรือ !แก้ไขสินค้า",
        value="แก้ไขข้อมูลสินค้า",
        inline=True
    )
    embed.add_field(
        name="/ประวัติ หรือ !ประวัติ",
        value="ดูประวัติการซื้อล่าสุด",
        inline=True
    )
    
    await interaction.response.send_message(embed=embed)

server_on()

# Run the bot
if __name__ == "__main__":
    bot.run(os.getenv('TOKEN'))
