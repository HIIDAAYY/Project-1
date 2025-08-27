import logging
import random
from models import SessionLocal, Product, Order
from config import snap

def init_db():
    db = SessionLocal()
    try:
        if db.query(Product).count() == 0:
            products_data = [
                {"name": "kemeja flanel", "stock": 15, "colors": ["merah", "biru"]},
                {"name": "celana chino", "stock": 0, "colors": ["hitam", "krem"]},
                {"name": "sepatu kets", "stock": 5, "colors": ["putih"]}
            ]
            for data in products_data:
                product = Product(name=data["name"], stock=data["stock"], colors=data["colors"])
                db.add(product)
            db.commit()
            logging.info("Data stok berhasil diinisialisasi.")
        else:
            logging.info("Data stok sudah ada di DB.")
    except Exception as e:
        logging.error(f"Gagal init DB: {e}")
    finally:
        db.close()

def get_product_info(input_str: str) -> str:
    input_str = input_str.replace("?", "").strip()
    parts = input_str.lower().split()
    
    if any(word in input_str.lower() for word in ["warna", "color", "colors"]):
        info_type = 'colors'
    elif any(word in input_str.lower() for word in ["ada", "stok", "stock"]):
        info_type = 'stock'
    else:
        info_type = 'all'
    
    stop_words = ['ada', 'stok', 'warna', 'apa', 'aja', 'berapa', 'info', 'lengkap', 'untuk', 'nih', 'yuk', 'punya', 'jual', 'apaan', 'stock', 'colors', 'all', 'semua']
    clean_parts = [p for p in parts if p not in stop_words]
    
    if info_type == 'colors' and clean_parts and clean_parts[-1] in ['apa', 'apaan']:
        clean_parts = clean_parts[:-1]
    
    clean_name = ' '.join(clean_parts).replace("flannel", "flanel").replace("flanelnya", "flanel").replace("chinonya", "chino").strip()
    logging.info(f"Query DB dengan nama: {clean_name}, type: {info_type}")
    
    db = SessionLocal()
    try:
        product = db.query(Product).filter(Product.name.ilike(f"%{clean_name}%")).first()
        if product:
            colors = ', '.join(product.colors) if product.colors else 'tidak ada'
            if info_type == 'stock':
                if product.stock == 0:
                    return f"Maaf, stok {product.name} habis saat ini."
                return f"Stok {product.name} ada {product.stock} pcs."
            elif info_type == 'colors':
                if product.stock == 0:
                    return f"Pilihan warna untuk {product.name}: {colors}. Maaf, stok habis saat ini."
                return f"Pilihan warna untuk {product.name}: {colors}."
            else:
                if product.stock == 0:
                    return f"Stok {product.name} 0 pcs. Warna: {colors}. Maaf, stok habis saat ini."
                return f"Stok {product.name} ada {product.stock} pcs. Warna: {colors}."
        return "Produk tidak ditemukan."
    except Exception as e:
        logging.error(f"Error query DB: {e}")
        return "Error akses database."
    finally:
        db.close()

def create_order(input_str: str, user_number: str) -> str:
    parts = input_str.lower().strip().split()
    if len(parts) < 2:
        logging.warning(f"Input pesanan tidak valid: {input_str}")
        return random.choice([
            "Mau berapa, Kak?",
            "Berapa jumlahnya, Kak?",
            "Mau pesan berapa unit, Kak?",
            "Jumlah pesanannya berapa, Kak?"
        ])
    if parts[0] in ["pesan", "order", "mau", "beli"]:  # Tambah keyword santai
        parts = parts[1:]
    if len(parts) < 2:
        logging.warning(f"Input pesanan tidak lengkap setelah hapus 'pesan': {input_str}")
        return random.choice([
            "Mau berapa, Kak?",
            "Berapa jumlahnya, Kak?",
            "Mau pesan berapa unit, Kak?",
            "Jumlah pesanannya berapa, Kak?"
        ])
    product_name = ' '.join(parts[:-1]).replace("flannel", "flanel").replace("flanelnya", "flanel").replace("chinonya", "chino")
    try:
        quantity = int(parts[-1])
        if quantity <= 0:
            raise ValueError("Jumlah harus lebih dari 0")
    except ValueError:
        logging.warning(f"Jumlah tidak valid: {parts[-1]}")
        return random.choice([
            "Mau berapa, Kak?",
            "Jumlahnya harus angka, Kak!",
            "Masukkan jumlah dalam angka, Kak!",
            "Berapa jumlahnya, Kak?"
        ])
    logging.info(f"Membuat pesanan: {product_name}, jumlah: {quantity}, user: {user_number}")
    db = SessionLocal()
    try:
        product = db.query(Product).filter(Product.name.ilike(f"%{product_name}%")).first()
        if not product:
            logging.warning(f"Produk tidak ditemukan: {product_name}")
            return "Produk tidak ditemukan, Kak."
        if product.stock < quantity:
            logging.warning(f"Stok tidak cukup: {product_name}, stok: {product.stock}, diminta: {quantity}")
            return f"Maaf, stok {product_name} hanya {product.stock} pcs."
        product.stock -= quantity
        order = Order(user_number=user_number, product_name=product_name, quantity=quantity)
        db.add(order)
        db.commit()
        logging.info(f"Order dibuat di DB: order-{order.id}")
        try:
            phone = user_number.replace('whatsapp:', '')
            logging.debug(f"Phone extracted for Midtrans: {phone}")  # Tambah debug phone
            if not phone or not phone.startswith('+'):
                logging.error("Phone invalid for Midtrans: {phone}")
                return "Maaf, nomor telepon tidak valid untuk pembayaran. Coba konfirmasi nomor Anda, Kak."
            transaction = snap.create_transaction({
                'transaction_details': {
                    'order_id': f'order-{order.id}',
                    'gross_amount': quantity * 50000
                },
                'item_details': [{
                    'id': product_name,
                    'price': 50000,
                    'quantity': quantity,
                    'name': product_name
                }],
                'customer_details': {
                    'phone': phone
                }
            })
            payment_link = transaction['redirect_url']
            logging.info(f"Pesanan dibuat: order-{order.id}, link: {payment_link}")
            return f"Pesanan {quantity} {product_name} berhasil! Link pembayaran: {payment_link}"
        except Exception as e:
            logging.error(f"Error Midtrans API: {str(e)}")  # Detail error
            return "Maaf, gagal membuat link pembayaran. Cek koneksi atau coba lagi nanti, Kak."
    except Exception as e:
        logging.error(f"Error membuat pesanan: {str(e)}")
        return "Maaf, gagal membuat pesanan. Coba lagi nanti, Kak."
    finally:
        db.close()