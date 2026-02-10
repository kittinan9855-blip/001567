from flask import Flask, render_template, request, redirect, url_for, session
import sqlite3
from datetime 
import timedelta
import os
import subprocess

# เช็กว่าถ้ายังไม่มีไฟล์ฐานข้อมูล ให้รันสร้างใหม่ทันที
if not os.path.exists('database.db'):
    subprocess.run(['python', 'init_db.py'])

app = Flask(__name__)
app.secret_key = 'BookingGG_SecretKey'
# ตั้งค่าให้จำการล็อกอิน 7 วัน
app.permanent_session_lifetime = timedelta(days=7) 

# ฟังก์ชันจัดรูปแบบราคา (ใส่ลูกน้ำ)
app.jinja_env.globals.update(format_price=lambda x: "{:,}".format(x) if x is not None else "0")

def get_db():
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    return conn

# --- 🔐 ส่วน Login / Logout ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        conn = get_db()
        user = conn.execute('SELECT * FROM users WHERE username = ? AND password = ?', (username, password)).fetchone()
        conn.close()
        
        if user:
            session.permanent = True # จำการล็อกอิน
            session['user_id'] = user['id']
            session['role'] = user['role']
            session['fullname'] = user['fullname']
            return redirect(url_for('admin_dashboard') if user['role'] == 'admin' else url_for('index'))
        else:
            return render_template('login.html', error="ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง")
            
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# --- 🔥 ส่วนสมัครสมาชิก (Register) ---
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        fullname = request.form['fullname']
        username = request.form['username']
        password = request.form['password']
        confirm_password = request.form['confirm_password']
        
        if password != confirm_password:
            return render_template('register.html', error="รหัสผ่านยืนยันไม่ตรงกัน")
        
        conn = get_db()
        try:
            # สมัครใหม่ role เป็น 'user' เสมอ
            conn.execute('INSERT INTO users (username, password, role, fullname) VALUES (?, ?, ?, ?)', 
                         (username, password, 'user', fullname))
            conn.commit()
            conn.close()
            return redirect(url_for('login')) # สมัครเสร็จเด้งไปหน้าล็อกอิน
        except sqlite3.IntegrityError:
            conn.close()
            return render_template('register.html', error="ชื่อผู้ใช้นี้มีคนใช้แล้ว")
            
    return render_template('register.html')

# --- 👤 ส่วน Profile + เปลี่ยนรหัสผ่าน ---
@app.route('/profile', methods=['GET', 'POST'])
def profile():
    if 'user_id' not in session: return redirect(url_for('login'))
    conn = get_db()
    
    if request.method == 'POST':
        session['fullname'] = request.form['fullname']
        conn.execute('UPDATE users SET fullname = ? WHERE id = ?', (request.form['fullname'], session['user_id']))
        conn.commit()
    
    user = conn.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],)).fetchone()
    conn.close()
    return render_template('profile.html', user=user)

@app.route('/change_password', methods=['GET', 'POST'])
def change_password():
    if 'user_id' not in session: return redirect(url_for('login'))
    
    if request.method == 'POST':
        old_password = request.form['old_password']
        new_password = request.form['new_password']
        confirm_new = request.form['confirm_new']
        
        conn = get_db()
        user = conn.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],)).fetchone()
        
        if user['password'] != old_password:
            conn.close()
            return render_template('change_password.html', error="รหัสผ่านเดิมไม่ถูกต้อง")
        
        if new_password != confirm_new:
            conn.close()
            return render_template('change_password.html', error="รหัสผ่านใหม่ไม่ตรงกัน")
            
        conn.execute('UPDATE users SET password = ? WHERE id = ?', (new_password, session['user_id']))
        conn.commit()
        conn.close()
        return redirect(url_for('profile'))
        
    return render_template('change_password.html')

# --- 🏠 หน้าหลัก ---
@app.route('/')
def index():
    conn = get_db()
    rooms = conn.execute('SELECT * FROM rooms').fetchall()
    conn.close()
    return render_template('index.html', rooms=rooms)

# --- 🏨 ดูห้องพัก ---
@app.route('/room/<int:id>')
def room_detail(id):
    conn = get_db()
    room_data = conn.execute('SELECT * FROM rooms WHERE id = ?', (id,)).fetchone()
    conn.close()
    if room_data is None: return redirect(url_for('index'))
    room = dict(room_data)
    image_list = [room['image_url']]
    if room['extra_images']: image_list.extend(room['extra_images'].split('|'))
    facilities_list = []
    if room['facilities']: facilities_list = room['facilities'].split('|')
    return render_template('room_detail.html', room=room, images=image_list, facilities=facilities_list)

# --- 📅 ฟอร์มจอง (เลือกวันเวลา) ---
@app.route('/booking_form/<int:room_id>')
def booking_form(room_id):
    if 'user_id' not in session: return redirect(url_for('login'))
    conn = get_db()
    room = conn.execute('SELECT * FROM rooms WHERE id = ?', (room_id,)).fetchone()
    conn.close()
    if room is None: return redirect(url_for('index'))
    return render_template('booking_form.html', room=room)

# --- 📝 บันทึกการจอง ---
@app.route('/book/<int:room_id>', methods=['POST'])
def book_room(room_id):
    if 'user_id' not in session: return redirect(url_for('login'))
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('INSERT INTO bookings (user_id, room_id, checkin_date, checkin_time) VALUES (?, ?, ?, ?)',
                 (session['user_id'], room_id, request.form['checkin_date'], request.form['checkin_time']))
    booking_id = cursor.lastrowid 
    conn.commit()
    conn.close()
    return redirect(url_for('payment', booking_id=booking_id))

# --- 💸 หน้าชำระเงิน (QR Code) ---
@app.route('/payment/<int:booking_id>')
def payment(booking_id):
    if 'user_id' not in session: return redirect(url_for('login'))
    conn = get_db()
    # ดึงข้อมูลการจอง + ราคา
    sql = '''SELECT bookings.*, rooms.name, rooms.price, rooms.image_url 
             FROM bookings JOIN rooms ON bookings.room_id = rooms.id WHERE bookings.id = ?'''
    booking = conn.execute(sql, (booking_id,)).fetchone()
    conn.close()
    if booking is None: return redirect(url_for('index'))
    return render_template('payment.html', booking=booking)

# --- 🎒 การเดินทางของฉัน ---
@app.route('/my_bookings')
def my_bookings():
    if 'user_id' not in session: return redirect(url_for('login'))
    conn = get_db()
    sql = '''SELECT bookings.id, bookings.checkin_date, bookings.checkin_time, bookings.status, 
             rooms.name, rooms.price, rooms.image_url 
             FROM bookings JOIN rooms ON bookings.room_id = rooms.id WHERE bookings.user_id = ?'''
    bookings = conn.execute(sql, (session['user_id'],)).fetchall()
    conn.close()
    return render_template('my_bookings.html', bookings=bookings)

@app.route('/cancel_my_booking/<int:id>')
def cancel_my_booking(id):
    if 'user_id' not in session: return redirect(url_for('login'))
    conn = get_db()
    conn.execute('DELETE FROM bookings WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    return redirect(url_for('my_bookings'))

# --- 👑 Admin ---
@app.route('/admin')
def admin_dashboard():
    if 'user_id' not in session or session.get('role') != 'admin': return redirect(url_for('login'))
    conn = get_db()
    sql = '''SELECT bookings.id, bookings.checkin_date, bookings.checkin_time, bookings.status, 
             rooms.name, rooms.price, rooms.image_url, users.fullname 
             FROM bookings JOIN rooms ON bookings.room_id = rooms.id JOIN users ON bookings.user_id = users.id'''
    all_bookings = conn.execute(sql).fetchall()
    conn.close()
    return render_template('admin_dashboard.html', bookings=all_bookings)

@app.route('/admin/cancel/<int:id>')
def cancel_booking(id):
    if session.get('role') != 'admin': return redirect(url_for('index'))
    conn = get_db()
    conn.execute('DELETE FROM bookings WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    return redirect(url_for('admin_dashboard'))

if __name__ == '__main__':
    app.run(debug=True)