"""
Management command: seed_data
Generates 12 months of realistic sales data and loads it into MySQL.
Usage: python manage.py seed_data
"""
import random
from datetime import date, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.contrib.auth.models import User

from forecasting.models import Category, Product, SalesRecord, ChatSession


CATEGORIES = [
    'Electronics', 'Clothing', 'Home & Kitchen', 'Sports & Fitness',
    'Books & Stationery', 'Beauty & Personal Care', 'Grocery', 'Toys & Games'
]

PRODUCTS = [
    # (name, sku, category, price, cost, stock, reorder_pt, reorder_qty, supplier, lead_days)
    ('Wireless Headphones', 'ELEC-001', 'Electronics', 2999, 1800, 150, 20, 50, 'AudioTech India', 7),
    ('Smartphone Case', 'ELEC-002', 'Electronics', 499, 200, 300, 30, 100, 'CaseMaster', 5),
    ('Laptop Stand', 'ELEC-003', 'Electronics', 1299, 700, 80, 10, 30, 'ErgoDesk', 10),
    ('USB-C Hub', 'ELEC-004', 'Electronics', 1799, 900, 120, 15, 50, 'TechHub', 7),
    ('Bluetooth Speaker', 'ELEC-005', 'Electronics', 3499, 2100, 60, 10, 25, 'SoundWave', 7),
    ('Men\'s T-Shirt', 'CLO-001', 'Clothing', 599, 250, 500, 50, 200, 'FabricPlus', 5),
    ('Women\'s Kurta', 'CLO-002', 'Clothing', 899, 400, 400, 40, 150, 'ThreadWorks', 5),
    ('Denim Jeans', 'CLO-003', 'Clothing', 1499, 700, 250, 30, 100, 'DenimCo', 7),
    ('Running Shoes', 'CLO-004', 'Clothing', 2499, 1300, 180, 20, 60, 'StepFit', 10),
    ('Non-Stick Pan', 'HK-001', 'Home & Kitchen', 1199, 600, 200, 20, 80, 'CookSmart', 7),
    ('Pressure Cooker', 'HK-002', 'Home & Kitchen', 2299, 1200, 100, 15, 40, 'HomeChef', 10),
    ('Water Bottle', 'HK-003', 'Home & Kitchen', 399, 150, 600, 60, 200, 'HydraLife', 5),
    ('Yoga Mat', 'SP-001', 'Sports & Fitness', 799, 350, 300, 30, 100, 'FitZone', 7),
    ('Dumbbells Set', 'SP-002', 'Sports & Fitness', 1999, 1100, 80, 10, 30, 'IronGrip', 10),
    ('Cricket Bat', 'SP-003', 'Sports & Fitness', 3999, 2500, 50, 8, 20, 'SportXcel', 14),
    ('Notebook Pack', 'BST-001', 'Books & Stationery', 299, 120, 800, 80, 300, 'PaperMill', 5),
    ('Gel Pens Set', 'BST-002', 'Books & Stationery', 199, 70, 1000, 100, 400, 'WriteRight', 3),
    ('Face Wash', 'BPC-001', 'Beauty & Personal Care', 349, 140, 400, 40, 150, 'GlowCare', 5),
    ('Shampoo 500ml', 'BPC-002', 'Beauty & Personal Care', 299, 120, 500, 50, 200, 'HairVita', 5),
    ('Basmati Rice 5kg', 'GRO-001', 'Grocery', 499, 320, 1000, 100, 500, 'GrainFresh', 3),
    ('Cooking Oil 1L', 'GRO-002', 'Grocery', 199, 130, 800, 80, 400, 'PureGold', 3),
    ('Instant Noodles', 'GRO-003', 'Grocery', 49, 25, 2000, 200, 1000, 'QuickBite', 3),
    ('Building Blocks', 'TOY-001', 'Toys & Games', 999, 500, 150, 20, 60, 'PlayWorld', 7),
    ('Board Game', 'TOY-002', 'Toys & Games', 1499, 700, 80, 10, 30, 'FunFirst', 10),
]

CHANNELS = ['online', 'in_store', 'wholesale']
REGIONS  = ['North', 'South', 'East', 'West', 'Central']

# Realistic Indian customer names and emails
CUSTOMERS = [
    ('Rahul Sharma', 'rahul.sharma@gmail.com'),
    ('Priya Patel', 'priya.patel@yahoo.com'),
    ('Amit Kumar', 'amit.kumar@outlook.com'),
    ('Sunita Rao', 'sunita.rao@gmail.com'),
    ('Vijay Nair', 'vijay.nair@hotmail.com'),
    ('Ananya Singh', 'ananya.singh@gmail.com'),
    ('Rajesh Gupta', 'rajesh.gupta@yahoo.com'),
    ('Meena Iyer', 'meena.iyer@gmail.com'),
    ('Sanjay Mehta', 'sanjay.mehta@outlook.com'),
    ('Kavitha Reddy', 'kavitha.reddy@gmail.com'),
    ('Arjun Verma', 'arjun.verma@yahoo.com'),
    ('Deepa Krishnan', 'deepa.krishnan@gmail.com'),
    ('Rohit Joshi', 'rohit.joshi@hotmail.com'),
    ('Nisha Pillai', 'nisha.pillai@gmail.com'),
    ('Suresh Bhat', 'suresh.bhat@outlook.com'),
]


class Command(BaseCommand):
    help = 'Seeds the database with 12 months of realistic retail sales data'

    def add_arguments(self, parser):
        parser.add_argument('--months', type=int, default=12, help='Number of months of history to generate')
        parser.add_argument('--clear', action='store_true', help='Clear existing data first')

    def handle(self, *args, **options):
        if options['clear']:
            self.stdout.write('Clearing existing data...')
            SalesRecord.objects.all().delete()
            Product.objects.all().delete()
            Category.objects.all().delete()

        self.stdout.write(self.style.SUCCESS('[OK] Seeding database...'))


        # Create superuser if not exists
        if not User.objects.filter(username='admin').exists():
            User.objects.create_superuser('admin', 'admin@retailiq.com', 'admin123')
            self.stdout.write('[+] Superuser created: admin / admin123')

        # Create categories
        cat_objects = {}
        for cat_name in CATEGORIES:
            cat, _ = Category.objects.get_or_create(name=cat_name)
            cat_objects[cat_name] = cat
        self.stdout.write(f'[+] {len(cat_objects)} categories created')

        # Create products
        product_objects = []
        for (name, sku, cat_name, price, cost, stock, rp, rq, supplier, lead) in PRODUCTS:
            product, _ = Product.objects.get_or_create(
                sku=sku,
                defaults={
                    'name': name,
                    'category': cat_objects[cat_name],
                    'price': Decimal(str(price)),
                    'cost_price': Decimal(str(cost)),
                    'stock': stock,
                    'reorder_point': rp,
                    'reorder_quantity': rq,
                    'supplier_name': supplier,
                    'supplier_email': f'orders@{supplier.lower().replace(" ", "")}.com',
                    'lead_time_days': lead,
                }
            )
            product_objects.append(product)
        self.stdout.write(f'[+] {len(product_objects)} products created')

        # Generate sales records using bulk_create for speed (50-100x faster over SSL)
        months = options['months']
        end_date = date.today()
        start_date = end_date - timedelta(days=months * 30)

        BATCH_SIZE = 500
        batch = []
        records_created = 0

        BASE_DEMAND = {
            'Electronics': (2, 12),
            'Clothing': (5, 25),
            'Home & Kitchen': (3, 18),
            'Sports & Fitness': (2, 10),
            'Books & Stationery': (10, 50),
            'Beauty & Personal Care': (5, 30),
            'Grocery': (20, 100),
            'Toys & Games': (2, 10),
        }

        current_date = start_date
        total_days = (end_date - start_date).days + 1
        self.stdout.write(f'Generating {total_days} days x {len(product_objects)} products...')

        while current_date <= end_date:
            dow_factor    = 1.4 if current_date.weekday() >= 5 else 1.0
            month_factor  = 1.5 if current_date.month in [10, 11, 12] else (
                             1.2 if current_date.month in [1, 8, 9] else 1.0)

            for product in product_objects:
                if random.random() < 0.6:
                    lo, hi   = BASE_DEMAND.get(product.category.name, (3, 15))
                    quantity = int(random.randint(lo, hi) * dow_factor * month_factor)
                    channel  = random.choices(CHANNELS, weights=[0.6, 0.3, 0.1])[0]
                    customer = random.choice(CUSTOMERS)

                    batch.append(SalesRecord(
                        product=product,
                        date=current_date,
                        quantity=quantity,
                        revenue=Decimal(str(quantity)) * product.price,
                        channel=channel,
                        region=random.choice(REGIONS),
                        customer_name=customer[0],
                        customer_email=customer[1],
                    ))
                    records_created += 1

                    # Flush batch to DB
                    if len(batch) >= BATCH_SIZE:
                        SalesRecord.objects.bulk_create(batch, ignore_conflicts=True)
                        self.stdout.write(f'  Inserted {records_created} records...')
                        batch = []

            current_date += timedelta(days=1)

        # Insert any remaining records
        if batch:
            SalesRecord.objects.bulk_create(batch, ignore_conflicts=True)

        self.stdout.write(f'[+] {records_created} sales records created across {months} months')
        self.stdout.write(self.style.SUCCESS('\n[DONE] Database seeding complete!'))
        self.stdout.write('Run: python manage.py train_models')
