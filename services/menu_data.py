"""Sample canteen menu. Used to seed demo mode and the MenuItems table.

Prices are whole rupees. The server always uses these stored prices; the browser never sets a price.
`emoji` is shown on the card when `image_url` is empty or an image fails to load.
The local SVG artwork is used by default for consistent, sharp menu illustrations.
"""

CATEGORIES = ["Breakfast", "Snacks", "Meals", "Beverages"]

SAMPLE_MENU = [
    {"item_id": "M001", "name": "Veg Sandwich", "category": "Snacks", "price": 60, "emoji": "🥪",
     "description": "Fresh vegetables, mint chutney and grilled bread.", "image_url": "/static/images/veg-sandwich.jpg", "available": True, "featured": False},
    {"item_id": "M002", "name": "Cheese Sandwich", "category": "Snacks", "price": 80, "emoji": "🧀",
     "description": "Toasted bread with melted cheese and tomato.", "image_url": "/static/images/cheese-sandwich.jpg", "available": True, "featured": True},
    {"item_id": "M003", "name": "Masala Dosa", "category": "Breakfast", "price": 70, "emoji": "🥞",
     "description": "Crispy dosa with spiced potato filling and chutney.", "image_url": "/static/images/masala-dosa.jpg", "available": True, "featured": True},
    {"item_id": "M004", "name": "Idli", "category": "Breakfast", "price": 40, "emoji": "⚪",
     "description": "Two soft idlis served with sambar and coconut chutney.", "image_url": "/static/images/idli.jpg", "available": True, "featured": False},
    {"item_id": "M005", "name": "Upma", "category": "Breakfast", "price": 35, "emoji": "🥣",
     "description": "Semolina upma with vegetables and curry leaves.", "image_url": "/static/images/upma.jpg", "available": True, "featured": False},
    {"item_id": "M006", "name": "Veg Fried Rice", "category": "Meals", "price": 100, "emoji": "🍛",
     "description": "Wok-tossed rice with vegetables and soy sauce.", "image_url": "/static/images/veg-fried-rice.jpg", "available": True, "featured": False},
    {"item_id": "M007", "name": "Paneer Meal", "category": "Meals", "price": 120, "emoji": "🍱",
     "description": "Paneer curry, dal, rice, two rotis and salad.", "image_url": "/static/images/paneer-meal.jpg", "available": True, "featured": True},
    {"item_id": "M008", "name": "Samosa", "category": "Snacks", "price": 20, "emoji": "🥟",
     "description": "Crisp pastry with spiced potato and peas.", "image_url": "/static/images/samosa.jpg", "available": True, "featured": False},
    {"item_id": "M009", "name": "Vada Pav", "category": "Snacks", "price": 25, "emoji": "🍔",
     "description": "Spiced potato fritter in a soft bun with chutneys.", "image_url": "/static/images/vada-pav.jpg", "available": False, "featured": False},
    {"item_id": "M010", "name": "Fresh Juice", "category": "Beverages", "price": 50, "emoji": "🥤",
     "description": "Seasonal fruit juice, freshly pressed.", "image_url": "/static/images/fresh-juice.jpg", "available": True, "featured": False},
    {"item_id": "M011", "name": "Tea", "category": "Beverages", "price": 15, "emoji": "🍵",
     "description": "Hot masala chai.", "image_url": "/static/images/tea.jpg", "available": True, "featured": False},
    {"item_id": "M012", "name": "Coffee", "category": "Beverages", "price": 25, "emoji": "☕",
     "description": "Filter coffee with milk.", "image_url": "/static/images/coffee.jpg", "available": True, "featured": False},
]
