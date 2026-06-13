"""
Management command: train_models
Trains Prophet and RandomForest models for all products.
Usage: python manage.py train_models
"""
import logging
from django.core.management.base import BaseCommand
from forecasting.models import Product

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Train Prophet and RandomForest demand forecasting models for all products'

    def add_arguments(self, parser):
        parser.add_argument('--product-id', type=int, help='Train only for a specific product ID')
        parser.add_argument('--model', choices=['prophet', 'rf', 'all'], default='all', help='Which model to train')

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('[START] Starting model training...'))

        if options['product_id']:
            products = Product.objects.filter(id=options['product_id'], is_active=True)
        else:
            products = Product.objects.filter(is_active=True)

        total = products.count()
        self.stdout.write(f'Training models for {total} products...\n')

        prophet_ok = 0
        rf_ok = 0

        # ── Train Prophet models ──────────────────────────────────────────────
        if options['model'] in ['prophet', 'all']:
            self.stdout.write('[PROPHET] Training Prophet models...')
            from forecasting.engine.pipeline import load_product_sales_df
            from forecasting.engine.prophet_model import ProphetDemandModel

            for i, product in enumerate(products, 1):
                self.stdout.write(f'  [{i}/{total}] {product.name}...', ending=' ')
                df = load_product_sales_df(product.id, days=365)

                if df.empty:
                    self.stdout.write(self.style.WARNING('No data, skipped.'))
                    continue

                pm = ProphetDemandModel(product.id)
                if pm.train(df[['ds', 'y']]):
                    pm.save()
                    prophet_ok += 1
                    self.stdout.write(self.style.SUCCESS(f'✓ ({len(df)} rows)'))
                else:
                    self.stdout.write(self.style.WARNING('Insufficient data, skipped.'))

        # ── Train RandomForest (global model) ─────────────────────────────────
        if options['model'] in ['rf', 'all']:
            self.stdout.write('\n[RF] Training RandomForest model (global)...')
            from forecasting.engine.pipeline import load_product_sales_df, build_rf_feature_matrix
            from forecasting.engine.rf_model import RandomForestDemandModel
            import numpy as np

            all_X, all_y = [], []
            for product in products:
                df = load_product_sales_df(product.id, days=365)
                if not df.empty:
                    try:
                        X, y = build_rf_feature_matrix(df, float(product.price), product.category.id if product.category else 0)
                        all_X.append(X)
                        all_y.append(y)
                    except Exception as e:
                        logger.warning("RF feature extraction failed for %s: %s", product.name, e)

            if all_X:
                X_combined = np.vstack(all_X)
                y_combined = np.concatenate(all_y)
                rf = RandomForestDemandModel()
                if rf.train(X_combined, y_combined):
                    rf.save()
                    rf_ok = 1
                    self.stdout.write(self.style.SUCCESS(f'  ✓ RF trained on {len(X_combined)} samples'))

        self.stdout.write(self.style.SUCCESS(
            f'\n[DONE] Training complete! Prophet: {prophet_ok}/{total} products | RF: {"OK" if rf_ok else "SKIP"}'
        ))
        self.stdout.write('Next: python manage.py runserver')
