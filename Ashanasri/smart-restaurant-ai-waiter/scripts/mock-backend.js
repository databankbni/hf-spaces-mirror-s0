/**
 * Local MOCK Django backend for testing the AI Waiter Service.
 *
 * It pretends to be the real backend so you can talk to the AI engine
 * end-to-end without the other PC. Serves a sample menu at:
 *
 *     GET /api/restaurants/:slug/menu/
 *
 * (Any slug works — it always returns this demo restaurant's menu.)
 *
 * Run:   npm run mock
 * Stop:  Ctrl + C
 */
const http = require('http');

const PORT = process.env.MOCK_PORT || 8000;

// ── Helper to keep each item short & consistent ─────────────────────────────
let _id = 0;
const item = (name, category, price, calories, tags, opts = {}) => ({
  id: `item-${String(++_id).padStart(3, '0')}`,
  name,
  description: opts.description || '',
  price,
  calories,
  ingredients: opts.ingredients || '',
  allergens: opts.allergens || '',
  tags,
  is_available: opts.is_available !== false, // available unless explicitly false
  category: { name: category },
  // Placeholder food photo per dish (real DB will provide actual URLs).
  image: `https://picsum.photos/seed/${encodeURIComponent(name)}/240/160`,
});

// ── 70 dishes across 12 categories ──────────────────────────────────────────
const menuItems = [
  // ───────── Breakfast ─────────
  item('Mandazi', 'Breakfast', 2000, 250, ['breakfast', 'popular'], { description: 'Soft East African fried doughnuts', ingredients: 'Wheat flour, coconut milk, sugar', allergens: 'gluten' }),
  item('Chai ya Tangawizi', 'Breakfast', 1500, 90, ['breakfast'], { description: 'Spiced ginger tea with milk', ingredients: 'Tea, ginger, milk, sugar', allergens: 'dairy' }),
  item('Uji wa Ulezi', 'Breakfast', 2500, 180, ['breakfast', 'healthy'], { description: 'Warm millet porridge', ingredients: 'Millet flour, water, sugar' }),
  item('Spanish Omelette', 'Breakfast', 6000, 320, ['breakfast'], { description: 'Fluffy omelette with peppers and onions', ingredients: 'Eggs, peppers, onions', allergens: 'eggs' }),
  item('Pancakes with Honey', 'Breakfast', 7000, 450, ['breakfast', 'popular'], { description: 'Stack of pancakes drizzled with honey', ingredients: 'Flour, eggs, milk, honey', allergens: 'gluten, eggs, dairy' }),
  item('Vitumbua', 'Breakfast', 3000, 210, ['breakfast', 'vegetarian'], { description: 'Sweet coconut rice cakes', ingredients: 'Rice flour, coconut, sugar', allergens: 'eggs' }),

  // ───────── Starters ─────────
  item('Beef Samosa', 'Starters', 3500, 280, ['popular'], { description: 'Crispy pastry filled with spiced minced beef', ingredients: 'Wheat pastry, beef, spices', allergens: 'gluten' }),
  item('Vegetable Samosa', 'Starters', 3000, 240, ['vegetarian'], { description: 'Crispy pastry filled with spiced vegetables', ingredients: 'Wheat pastry, potato, peas', allergens: 'gluten' }),
  item('Bhajia', 'Starters', 4000, 300, ['vegetarian', 'vegan', 'spicy'], { description: 'Spiced potato fritters', ingredients: 'Potato, gram flour, chili' }),
  item('Spring Rolls', 'Starters', 4500, 260, ['vegetarian'], { description: 'Crispy rolls with vegetable filling', ingredients: 'Wheat wrapper, cabbage, carrot', allergens: 'gluten, soy' }),
  item('Chicken Wings', 'Starters', 8000, 430, ['popular', 'spicy'], { description: 'Grilled wings tossed in hot sauce', ingredients: 'Chicken, chili, garlic' }),
  item('Garlic Bread', 'Starters', 4000, 350, ['vegetarian'], { description: 'Toasted bread with garlic butter', ingredients: 'Bread, garlic, butter', allergens: 'gluten, dairy' }),

  // ───────── Soups ─────────
  item('Vegetable Soup', 'Soups', 5000, 150, ['vegetarian', 'vegan', 'low-calorie', 'healthy'], { description: 'Light garden vegetable soup', ingredients: 'Carrots, peas, celery, herbs' }),
  item('Chicken Soup', 'Soups', 6000, 220, ['healthy'], { description: 'Clear chicken broth with vegetables', ingredients: 'Chicken, carrots, onions' }),
  item('Pumpkin Soup', 'Soups', 5500, 180, ['vegetarian', 'low-calorie', 'healthy'], { description: 'Creamy roasted pumpkin soup', ingredients: 'Pumpkin, cream, onion', allergens: 'dairy' }),
  item('Supu ya Ndizi', 'Soups', 5000, 200, ['healthy'], { description: 'Traditional green banana soup', ingredients: 'Green banana, beef broth, herbs' }),
  item('Tomato Soup', 'Soups', 5000, 160, ['vegetarian', 'vegan', 'low-calorie'], { description: 'Rich roasted tomato soup', ingredients: 'Tomato, basil, onion' }),

  // ───────── Salads ─────────
  item('Kachumbari', 'Salads', 3000, 90, ['vegetarian', 'vegan', 'low-calorie', 'healthy'], { description: 'Fresh tomato and onion salad', ingredients: 'Tomato, onion, chili, lime' }),
  item('Garden Salad', 'Salads', 5000, 120, ['vegetarian', 'vegan', 'low-calorie', 'healthy'], { description: 'Mixed greens with light dressing', ingredients: 'Lettuce, cucumber, tomato' }),
  item('Greek Salad', 'Salads', 7000, 280, ['vegetarian', 'healthy'], { description: 'Salad with feta and olives', ingredients: 'Cucumber, tomato, feta, olives', allergens: 'dairy' }),
  item('Avocado Salad', 'Salads', 7500, 320, ['vegetarian', 'vegan', 'healthy'], { description: 'Creamy avocado with greens', ingredients: 'Avocado, lettuce, lime' }),
  item('Fruit Salad', 'Salads', 6000, 220, ['vegetarian', 'vegan', 'low-calorie', 'healthy'], { description: 'Fresh seasonal fruit medley', ingredients: 'Mango, pineapple, banana, watermelon' }),

  // ───────── Swahili Specials ─────────
  item('Pilau', 'Swahili Specials', 15000, 650, ['popular', 'lunch'], { description: 'Fragrant spiced rice cooked with tender beef', ingredients: 'Rice, beef, pilau masala, onions' }),
  item('Beef Biryani', 'Swahili Specials', 16000, 700, ['popular', 'spicy'], { description: 'Layered spiced rice with beef', ingredients: 'Rice, beef, biryani spices', allergens: 'dairy' }),
  item('Wali wa Nazi', 'Swahili Specials', 8000, 400, ['vegetarian', 'vegan'], { description: 'Coconut rice', ingredients: 'Rice, coconut milk' }),
  item('Mchuzi wa Samaki', 'Swahili Specials', 14000, 480, ['spicy', 'healthy'], { description: 'Coastal fish curry', ingredients: 'Fish, coconut, tamarind, chili', allergens: 'fish' }),
  item('Ugali na Maharage', 'Swahili Specials', 7000, 520, ['vegetarian', 'vegan'], { description: 'Maize meal with stewed beans', ingredients: 'Maize flour, kidney beans' }),
  item('Mishkaki', 'Swahili Specials', 9000, 380, ['popular', 'spicy'], { description: 'Grilled marinated beef skewers', ingredients: 'Beef, garlic, chili, spices' }),

  // ───────── Main Dishes ─────────
  item('Beef Stew', 'Main Dishes', 12000, 560, ['lunch'], { description: 'Slow-cooked beef in rich gravy', ingredients: 'Beef, tomato, onion, potato' }),
  item('Chicken Curry', 'Main Dishes', 13000, 540, ['popular', 'spicy'], { description: 'Tender chicken in spiced curry sauce', ingredients: 'Chicken, curry spices, tomato' }),
  item('Butter Chicken', 'Main Dishes', 15000, 720, ['popular'], { description: 'Creamy tomato butter chicken', ingredients: 'Chicken, butter, cream, tomato', allergens: 'dairy' }),
  item('Beef Burger', 'Main Dishes', 11000, 780, ['popular'], { description: 'Juicy beef patty with cheese', ingredients: 'Beef, bun, cheese, lettuce', allergens: 'gluten, dairy' }),
  item('Spaghetti Bolognese', 'Main Dishes', 12000, 650, [], { description: 'Pasta in rich beef and tomato sauce', ingredients: 'Pasta, beef, tomato', allergens: 'gluten' }),
  item('Chicken Biryani', 'Main Dishes', 14000, 680, ['popular', 'spicy'], { description: 'Spiced layered rice with chicken', ingredients: 'Rice, chicken, biryani spices', allergens: 'dairy' }),
  item('Pilau na Kuku', 'Main Dishes', 14000, 620, ['popular'], { description: 'Spiced pilau rice served with chicken', ingredients: 'Rice, chicken, pilau masala' }),
  item('Chips Mayai', 'Main Dishes', 6000, 480, ['popular'], { description: 'Tanzanian chips omelette', ingredients: 'Potato, eggs, onion', allergens: 'eggs' }),

  // ───────── Grills & BBQ ─────────
  item('Nyama Choma', 'Grills & BBQ', 20000, 800, ['popular', 'spicy'], { description: 'Charcoal-grilled spiced beef', ingredients: 'Beef, chili, salt' }),
  item('Kuku Choma', 'Grills & BBQ', 18000, 650, ['popular'], { description: 'Grilled marinated chicken', ingredients: 'Chicken, garlic, lemon' }),
  item('Mbuzi Choma', 'Grills & BBQ', 22000, 720, ['spicy'], { description: 'Grilled goat meat', ingredients: 'Goat, spices, chili' }),
  item('Grilled Pork Ribs', 'Grills & BBQ', 19000, 850, [], { description: 'BBQ-glazed pork ribs', ingredients: 'Pork, bbq sauce' }),
  item('Mixed Grill Platter', 'Grills & BBQ', 30000, 1100, ['popular'], { description: 'Beef, chicken and sausages platter', ingredients: 'Beef, chicken, sausage' }),
  item('Mishkaki ya Nyama', 'Grills & BBQ', 9000, 400, ['spicy'], { description: 'Grilled beef skewers', ingredients: 'Beef, chili, garlic' }),

  // ───────── Seafood ─────────
  item('Grilled Tilapia', 'Seafood', 18000, 420, ['healthy'], { description: 'Whole tilapia grilled with lemon', ingredients: 'Tilapia, lemon, garlic', allergens: 'fish' }),
  item('Fish & Chips', 'Seafood', 15000, 620, ['popular'], { description: 'Battered fish fillet with fries', ingredients: 'Fish, batter, potato', allergens: 'fish, gluten' }),
  item('Prawns Masala', 'Seafood', 24000, 480, ['spicy'], { description: 'Prawns in spiced masala sauce', ingredients: 'Prawns, masala, tomato', allergens: 'shellfish' }),
  item('Coconut Fish Curry', 'Seafood', 17000, 520, ['spicy', 'healthy'], { description: 'Fish simmered in coconut curry', ingredients: 'Fish, coconut milk, spices', allergens: 'fish' }),
  item('Calamari', 'Seafood', 16000, 380, [], { description: 'Lightly fried squid rings', ingredients: 'Squid, flour, lemon', allergens: 'shellfish, gluten' }),
  item('Pweza wa Nazi', 'Seafood', 21000, 460, ['spicy', 'healthy'], { description: 'Octopus in coconut sauce', ingredients: 'Octopus, coconut, chili', allergens: 'shellfish' }),

  // ───────── Vegetarian & Vegan ─────────
  item('Ugali na Mboga', 'Vegetarian & Vegan', 7000, 450, ['vegetarian', 'vegan', 'healthy'], { description: 'Maize meal with sautéed greens', ingredients: 'Maize flour, spinach, tomato' }),
  item('Vegetable Curry', 'Vegetarian & Vegan', 9000, 380, ['vegetarian', 'vegan', 'spicy', 'healthy'], { description: 'Mixed vegetables in curry sauce', ingredients: 'Vegetables, curry spices, coconut' }),
  item('Chickpea Stew', 'Vegetarian & Vegan', 8500, 420, ['vegetarian', 'vegan', 'healthy'], { description: 'Hearty spiced chickpea stew', ingredients: 'Chickpeas, tomato, onion' }),
  item('Lentil Dahl', 'Vegetarian & Vegan', 8000, 360, ['vegetarian', 'vegan', 'healthy', 'low-calorie'], { description: 'Spiced red lentil dahl', ingredients: 'Lentils, turmeric, garlic' }),
  item('Grilled Vegetable Skewers', 'Vegetarian & Vegan', 9000, 280, ['vegetarian', 'vegan', 'low-calorie', 'healthy'], { description: 'Char-grilled seasonal vegetables', ingredients: 'Peppers, zucchini, mushroom' }),
  item('Tofu Stir Fry', 'Vegetarian & Vegan', 10000, 400, ['vegetarian', 'vegan', 'healthy'], { description: 'Tofu and vegetables in soy glaze', ingredients: 'Tofu, vegetables, soy sauce', allergens: 'soy' }),

  // ───────── Sides ─────────
  item('Chapati', 'Sides', 2000, 300, ['popular', 'vegetarian'], { description: 'Soft layered flatbread', ingredients: 'Wheat flour, oil', allergens: 'gluten' }),
  item('French Fries', 'Sides', 5000, 380, ['popular', 'vegetarian', 'vegan'], { description: 'Crispy golden potato fries', ingredients: 'Potato, salt' }),
  item('Plain Rice', 'Sides', 4000, 350, ['vegetarian', 'vegan'], { description: 'Steamed white rice', ingredients: 'Rice' }),
  item('Ndizi Kaanga', 'Sides', 4000, 320, ['vegetarian', 'vegan'], { description: 'Fried sweet plantain', ingredients: 'Plantain, oil' }),
  item('Naan Bread', 'Sides', 3500, 290, ['vegetarian'], { description: 'Soft oven-baked flatbread', ingredients: 'Flour, yogurt', allergens: 'gluten, dairy' }),

  // ───────── Desserts ─────────
  item('Fruit Bowl', 'Desserts', 6000, 220, ['vegetarian', 'vegan', 'low-calorie', 'healthy'], { description: 'Fresh seasonal fruit, chilled', ingredients: 'Mango, watermelon, pineapple' }),
  item('Ice Cream', 'Desserts', 5000, 300, ['vegetarian', 'popular'], { description: 'Vanilla ice cream scoops', ingredients: 'Milk, cream, sugar', allergens: 'dairy' }),
  item('Chocolate Cake', 'Desserts', 7000, 480, ['vegetarian', 'popular'], { description: 'Rich moist chocolate cake', ingredients: 'Flour, cocoa, eggs, butter', allergens: 'gluten, eggs, dairy' }),
  item('Kashata', 'Desserts', 4000, 260, ['vegetarian', 'vegan'], { description: 'Coconut and peanut candy', ingredients: 'Coconut, peanuts, sugar', allergens: 'nuts' }),
  item('Mango Mousse', 'Desserts', 6500, 310, ['vegetarian'], { description: 'Light whipped mango dessert', ingredients: 'Mango, cream, sugar', allergens: 'dairy' }),

  // ───────── Beverages ─────────
  item('Fresh Mango Juice', 'Beverages', 4000, 160, ['vegetarian', 'vegan', 'healthy'], { description: 'Freshly blended mango juice', ingredients: 'Mango, water' }),
  item('Passion Juice', 'Beverages', 4000, 140, ['vegetarian', 'vegan', 'healthy'], { description: 'Tangy fresh passion fruit juice', ingredients: 'Passion fruit, water, sugar' }),
  item('Soda', 'Beverages', 2000, 150, [], { description: 'Assorted soft drinks', ingredients: 'Carbonated water, sugar' }),
  item('Bottled Water', 'Beverages', 1500, 0, ['low-calorie', 'healthy', 'vegan'], { description: '500ml mineral water', ingredients: 'Water' }),
  item('Coffee', 'Beverages', 3000, 60, ['vegetarian'], { description: 'Freshly brewed coffee', ingredients: 'Coffee, milk', allergens: 'dairy' }),
  item('Masala Tea', 'Beverages', 2500, 90, ['vegetarian', 'popular'], { description: 'Spiced milk tea', ingredients: 'Tea, milk, spices', allergens: 'dairy' }),

  // ───────── A couple of SOLD-OUT items (to test availability handling) ─────────
  item('Lobster Thermidor', 'Seafood', 45000, 600, ['popular'], { description: 'Grilled lobster in creamy sauce', ingredients: 'Lobster, cream, cheese', allergens: 'shellfish, dairy', is_available: false }),
  item('Seasonal Special', 'Main Dishes', 18000, 700, ['popular'], { description: "Chef's seasonal creation (currently unavailable)", ingredients: 'Varies', is_available: false }),
];

const restaurant = {
  name: 'Demo Grand Restaurant',
  slug: 'demo-grand-restaurant',
  description: 'A sample restaurant for testing the AI Waiter.',
};

// Exported so the demo-mode data file can be generated from this single source.
module.exports = { restaurant, menuItems };

if (require.main === module) {
  const server = http.createServer((req, res) => {
    if (/^\/api\/restaurants\/.+\/menu\/?$/.test(req.url || '')) {
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ restaurant, menuItems }));
      console.log(`[mock] 200  ${req.method} ${req.url}  (${menuItems.length} items)`);
    } else {
      res.writeHead(404, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ detail: 'Not found' }));
      console.log(`[mock] 404  ${req.method} ${req.url}`);
    }
  });

  server.listen(PORT, () => {
    console.log('────────────────────────────────────────────────');
    console.log(' MOCK Restaurant Backend (for AI Waiter testing)');
    console.log('────────────────────────────────────────────────');
    console.log(` Listening:  http://localhost:${PORT}`);
    console.log(` Menu:       GET /api/restaurants/:slug/menu/`);
    console.log(` Items:      ${menuItems.length} dishes`);
    console.log(` Try slug:   demo-grand-restaurant`);
    console.log(' Press Ctrl+C to stop.');
  });
}
