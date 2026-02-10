from flask import Flask, render_template, request, redirect, url_for, session
import sqlite3

app = Flask(__name__)
app.secret_key = 'BookingGG_SecretKey'
# ฟังก์ชันจัดรูปแบบราคา (ใส่ลูกน้ำ)
app.jinja_env.globals.update(format_price=lambda x: "{:,}".format(x))

def get_db():
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    return conn

# --- Login / Logout ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        conn = get_db()
        user = conn.execute('SELECT * FROM users WHERE username = ? AND password = ?', (username, password)).fetchone()
        conn.close()
        if user:
            session['user_id'] = user['id']
            session['role'] = user['role']
            session['fullname'] = user['fullname']
            return redirect(url_for('admin_dashboard') if user['role'] == 'admin' else url_for('index'))
        else:
            return render_template('login.html', error="รหัสผ่านไม่ถูกต้อง!")
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# --- Profile ---
@app.route('/profile', methods=['GET', 'POST'])
def profile():
    if 'user_id' not in session: return redirect(url_for('login'))
    conn = get_db()
    if request.method == 'POST':
        session['fullname'] = request.form['fullname']
        conn.execute('UPDATE users SET fullname = ? WHERE id = ?', (request.form['fullname'], session['user_id']))
        conn.commit()
        conn.close()
        return redirect(url_for('index'))
    user = conn.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],)).fetchone()
    conn.close()
    return render_template('profile.html', user=user)

# --- Home ---
@app.route('/')
def index():
    conn = get_db()
    rooms = conn.execute('SELECT * FROM rooms').fetchall()
    conn.close()
    return render_template('index.html', rooms=rooms)

# --- Room Detail ---
@app.route('/room/<int:id>')
def room_detail(id):
    conn = get_db()
    room_data = conn.execute('SELECT * FROM rooms WHERE id = ?', (id,)).fetchone()
    conn.close()
    if room_data is None: return "ไม่พบห้องพัก", 404
    
    room = dict(room_data)
    
    # แยกรูปภาพ
    image_list = [room['image_url']]
    if room['extra_images']:
        image_list.extend(room['extra_images'].split('|'))
    
    # แยกสิ่งอำนวยความสะดวก
    facilities_list = []
    if room['facilities']:
        facilities_list = room['facilities'].split('|')
        
    return render_template('room_detail.html', room=room, images=image_list, facilities=facilities_list)

# --- 🔥 ระบบจอง (กดแล้วไปหน้าจ่ายเงิน) ---
@app.route('/book/<int:room_id>', methods=['POST'])
def book_room(room_id):
    if 'user_id' not in session: return redirect(url_for('login'))
    
    checkin_date = request.form['checkin_date']
    checkin_time = request.form['checkin_time']
    
    conn = get_db()
    cursor = conn.cursor()
    # บันทึกการจองลงฐานข้อมูลก่อน
    cursor.execute('INSERT INTO bookings (user_id, room_id, checkin_date, checkin_time) VALUES (?, ?, ?, ?)',
                 (session['user_id'], room_id, checkin_date, checkin_time))
    # ดึง ID ของการจองล่าสุดมา เพื่อส่งไปหน้าจ่ายเงิน
    booking_id = cursor.lastrowid 
    conn.commit()
    conn.close()
    
    # เด้งไปหน้าชำระเงิน
    return redirect(url_for('payment', booking_id=booking_id))

# --- 🔥 หน้าชำระเงิน (เพิ่มใหม่) ---
@app.route('/payment/<int:booking_id>')
def payment(booking_id):
    if 'user_id' not in session: return redirect(url_for('login'))
    
    conn = get_db()
    # ดึงข้อมูลใบจอง + ชื่อห้อง + ราคา มาแสดง
    sql = '''
        SELECT bookings.*, rooms.name, rooms.price, rooms.image_url
        FROM bookings 
        JOIN rooms ON bookings.room_id = rooms.id 
        WHERE bookings.id = ?
    '''
    booking = conn.execute(sql, (booking_id,)).fetchone()
    conn.close()
    
    return render_template('payment.html', booking=booking)

# --- My Bookings ---
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
    if conn.execute('SELECT * FROM bookings WHERE id = ? AND user_id = ?', (id, session['user_id'])).fetchone():
        conn.execute('DELETE FROM bookings WHERE id = ?', (id,))
        conn.commit()
    conn.close()
    return redirect(url_for('my_bookings'))

# --- Admin ---
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