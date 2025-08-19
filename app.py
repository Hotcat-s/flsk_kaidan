from flask import Flask, render_template, session, request, redirect, url_for, flash, make_response
import pymysql
import re
import os
from functools import wraps
from io import BytesIO
import datetime

# 以下是打印表格的库
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# 参考链接  https://blog.csdn.net/wuyomhchang/article/details/131095753
app = Flask(__name__)
app.secret_key = os.urandom(24)
db = pymysql.connect(host='localhost', port=3306, user='root', password='root', database='sale_management',
                     charset='utf8')
cursor = db.cursor()
users = []
sale_name = []


# 限制某些需要登录才能访问
# 登出
# session.pop('login', None)

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get('login') != 'OK':  # 检查 session 中的 'login' 是否设置为 'OK'
            flash('请先登录后再进行操作', 'error')
            return redirect(url_for('login'))  # 如果没有登录，重定向到登录页面
        return f(*args, **kwargs)

    return decorated_function


@app.route('/', methods=["GET", "POST"])
def login():
    # 初始化变量
    msg = ''
    user = ''
    
    # 增加会话保护机制(GET请求时清空session，确保用户重新登录)
    if request.method == 'GET':
        session['login'] = ''
    
    if request.method == 'POST':
        user = request.values.get("user", "").strip()
        pwd = request.values.get("pwd", "").strip()
        
        # 检查是否为空输入
        if not user or not pwd:
            msg = '请输入用户名和密码'
            return render_template('login.html', msg=msg, user=user)
        
        # 防止sql注入,利用正则表达式进行输入判断
        result_user = re.search(r"^[a-zA-Z]+$", user)  # 限制用户名为全字母
        result_pwd = re.search(r"^[a-zA-Z\d]+$", pwd)  # 限制密码为 字母和数字的组合
        
        if result_user is None or result_pwd is None:  # 输入验证不通过
            msg = '用户名只能包含字母，密码只能包含字母和数字'
            return render_template('login.html', msg=msg, user=user)
        
        try:
            # 正则验证通过后与数据库中数据进行比较
            sql1 = "select * from user where admin_name=%s and admin_password=%s"
            cursor.execute(sql1, (user, pwd))

            # 并用fetchone()获取查询的第一个结果
            result = cursor.fetchone()

            # 匹配得到结果即管理员数据库中存在此管理员
            if result:
                # 登陆成功
                session['login'] = 'OK'
                users.append(user)  # 存储登陆成功的用户名用于显示
                
                # 查找user对应的sale_name
                sql = "select sale_name from user where admin_name=%s"
                cursor.execute(sql, (user,))
                sale_name1 = cursor.fetchall()
                if sale_name1:
                    sale_name.append(sale_name1[0][0])
                
                flash('登录成功！', 'success')
                return redirect(url_for('goodslist'))
            else:
                msg = '用户名或密码错误'
                
        except Exception as e:
            msg = '登录过程中发生错误，请稍后重试'
            print(f"Login error: {e}")
    
    return render_template('login.html', msg=msg, user=user)


@app.route('/logout')
def logout():
    """登出功能 - 清除会话并重定向到登录页面"""
    session.pop('login', None)  # 安全地移除login会话
    # 清空用户相关的全局变量
    users.clear()
    sale_name.clear()
    flash('您已成功登出', 'success')
    return redirect(url_for('login'))



# 展示已经添加的商品有哪些
@app.route('/goodslist')
@app.route('/goodslist/<int:page>')
@app.route('/goodslist/category/<int:category_id>')
@app.route('/goodslist/category/<int:category_id>/<int:page>')
@login_required
def goodslist(page=1, category_id=None):
    per_page = 10  # 每页显示10个商品
    offset = (page - 1) * per_page
    
    # 获取搜索关键词
    search_keyword = request.args.get('search', '').strip()
    
    try:
        # 获取所有类别用于下拉框
        categories_sql = "SELECT id, name FROM categories ORDER BY name"
        cursor.execute(categories_sql)
        categories = cursor.fetchall()
        
        # 构建查询条件
        where_conditions = []
        query_params = []
        
        # 添加类别筛选条件
        if category_id:
            where_conditions.append("category_id = %s")
            query_params.append(category_id)
        
        # 添加搜索条件
        if search_keyword:
            where_conditions.append("goods_name LIKE %s")
            query_params.append(f"%{search_keyword}%")
        
        # 构建WHERE子句
        where_clause = ""
        if where_conditions:
            where_clause = "WHERE " + " AND ".join(where_conditions)
        
        # 获取商品总数
        count_sql = f"SELECT COUNT(*) FROM goods_list {where_clause}"
        cursor.execute(count_sql, tuple(query_params))
        total_count = cursor.fetchone()[0]
        
        # 获取商品数据 - 使用简化查询
        goods_sql_simple = f"""
        SELECT id, goods_name, price, category_id
        FROM goods_list 
        {where_clause}
        LIMIT %s OFFSET %s
        """
        cursor.execute(goods_sql_simple, tuple(query_params + [per_page, offset]))
        simple_result = cursor.fetchall()
        
        # 手动构建最终结果
        if simple_result:
            goods_list_manual = []
            for item in simple_result:
                # 获取每个商品的类别名称
                category_name_sql = "SELECT name FROM categories WHERE id = %s"
                cursor.execute(category_name_sql, (item[3],))
                category_name_result = cursor.fetchone()
                category_name = category_name_result[0] if category_name_result else "未分类"
                
                # (id, goods_name, price, category_name, category_id)
                goods_list_manual.append((item[0], item[1], item[2], category_name, item[3]))
            
            goods_list = tuple(goods_list_manual)
        else:
            goods_list = ()
        
        # 设置当前类别名称
        if category_id:
            current_category_sql = "SELECT name FROM categories WHERE id = %s"
            cursor.execute(current_category_sql, (category_id,))
            current_category = cursor.fetchone()
            current_category_name = current_category[0] if current_category else "未知类别"
        else:
            current_category_name = "全部"

            
    except Exception as e:
        print(f"Error in goodslist function: {e}")
        categories = []
        goods_list = []
        total_count = 0
        current_category_name = "错误"
    
    # 计算总页数
    total_pages = (total_count + per_page - 1) // per_page
    
    # 计算分页信息
    has_prev = page > 1
    has_next = page < total_pages
    prev_page = page - 1 if has_prev else None
    next_page = page + 1 if has_next else None
    
    # 计算显示的页码范围（显示当前页前后各2页）
    start_page = max(1, page - 2)
    end_page = min(total_pages, page + 2)
    page_range = list(range(start_page, end_page + 1))
    
    # 计算当前显示的记录范围
    start_record = offset + 1 if goods_list else 0
    end_record = min(offset + per_page, total_count)
    
    pagination_info = {
        'page': page,
        'total_pages': total_pages,
        'total_count': total_count,
        'per_page': per_page,
        'has_prev': has_prev,
        'has_next': has_next,
        'prev_page': prev_page,
        'next_page': next_page,
        'page_range': page_range,
        'start_record': start_record,
        'end_record': end_record
    }
    
    return render_template('goodslist.html', 
                         goods_list=goods_list, 
                         pagination=pagination_info,
                         categories=categories,
                         current_category_id=category_id,
                         current_category_name=current_category_name,
                         search_keyword=search_keyword)


# #设置添加商品信息的路由
@app.route('/add_goods', methods=["GET", "POST"])
def add_goods():
    # 仍然展示已经存在的商品信息
    # goods_list = []
    # sql2 = "select * from goods_list"
    # data = cursor.execute(sql2)
    # list = cursor.fetchall()
    # for item in list:
    #     goods_list.append(item)
    if request.method == "POST":
        goodsname = request.values.get("goods_name", '')
        price1 = request.values.get("price", '')
        # print(type(goodsname))
        sql = "insert into goods_list(goods_name,price) values('" + goodsname + "'," + price1 + ")"
        # print(sql)
        cursor.execute(sql)
        db.commit()
        # 如果插入成功的话，那么就跳转到商品信息的路由
        return redirect(url_for('goodslist'))

    return render_template('add_goods.html')


# 设置的删除商品信息的路由
@app.route('/delete_goods/<int:goods_id>')
@login_required
def delete_goods(goods_id):
    try:
        # 执行删除操作
        sql = "DELETE FROM goods_list WHERE id = %s"
        # 这个 tuple 是必须的，即使只有一个参数
        cursor.execute(sql, (goods_id,))
        # 事务提交
        db.commit()
        if cursor.rowcount > 0:
            flash('商品删除成功！', 'success')
        else:
            flash('未找到该商品或商品已被删除。', 'error')
    except pymysql.Error as e:
        # 回滚事务
        db.rollback()
        flash('数据库操作失败，删除失败。', 'error')
        print(f"Delete error: {e}")
    
    # 删除后重定向到商品列表页面
    return redirect(url_for('goodslist'))


# 批量删除商品
@app.route('/batch_delete_goods', methods=['POST'])
@login_required
def batch_delete_goods():
    try:
        # 获取要删除的商品ID列表
        goods_ids = request.form.getlist('goods_ids')
        
        if not goods_ids:
            return {'success': False, 'message': '请选择要删除的商品'}
        
        # 验证所有ID都是数字
        try:
            goods_ids = [int(id) for id in goods_ids]
        except ValueError:
            return {'success': False, 'message': '无效的商品ID'}
        
        # 构建删除SQL
        placeholders = ','.join(['%s'] * len(goods_ids))
        sql = f"DELETE FROM goods_list WHERE id IN ({placeholders})"
        
        # 执行删除操作
        cursor.execute(sql, goods_ids)
        db.commit()
        
        deleted_count = cursor.rowcount
        
        if deleted_count > 0:
            return {
                'success': True, 
                'message': f'成功删除 {deleted_count} 个商品',
                'deleted_count': deleted_count
            }
        else:
            return {'success': False, 'message': '没有找到要删除的商品'}
            
    except pymysql.Error as e:
        # 回滚事务
        db.rollback()
        print(f"Batch delete error: {e}")
        return {'success': False, 'message': '数据库操作失败，删除失败'}
    except Exception as e:
        print(f"Batch delete error: {e}")
        return {'success': False, 'message': '删除操作失败'}


# 商品编辑功能
@app.route('/edit_goods/<int:goods_id>', methods=["GET", "POST"])
@login_required
def edit_goods(goods_id):
    if request.method == "POST":
        goods_name = request.values.get("goods_name", "").strip()
        price = request.values.get("price", "").strip()
        category_id = request.values.get("category_id", "")
        
        if not goods_name or not price:
            flash('商品名称和价格不能为空', 'error')
            return redirect(url_for('goodslist'))
        
        try:
            price = float(price)
            if price <= 0:
                flash('价格必须大于0', 'error')
                return redirect(url_for('goodslist'))
        except ValueError:
            flash('价格格式不正确', 'error')
            return redirect(url_for('goodslist'))
        
        try:
            sql = "UPDATE goods_list SET goods_name=%s, price=%s, category_id=%s WHERE id=%s"
            cursor.execute(sql, (goods_name, price, category_id if category_id else None, goods_id))
            db.commit()
            if cursor.rowcount > 0:
                flash('商品修改成功！', 'success')
            else:
                flash('商品不存在或修改失败', 'error')
        except Exception as e:
            db.rollback()
            flash('修改商品时发生错误', 'error')
            print(f"Edit error: {e}")
    
    return redirect(url_for('goodslist'))


# AJAX获取商品信息接口
@app.route('/api/goods/<int:goods_id>')
def get_goods(goods_id):
    try:
        sql = """
        SELECT g.id, g.goods_name, g.price, g.category_id, c.name as category_name
        FROM goods_list g 
        LEFT JOIN categories c ON g.category_id = c.id 
        WHERE g.id = %s
        """
        cursor.execute(sql, (goods_id,))
        goods = cursor.fetchone()
        
        if goods:
            return {
                'success': True,
                'data': {
                    'id': goods[0],
                    'goods_name': goods[1],
                    'price': goods[2],
                    'category_id': goods[3],
                    'category_name': goods[4]
                }
            }
        else:
            return {'success': False, 'message': '商品不存在'}
    except Exception as e:
        print(f"Get goods error: {e}")
        return {'success': False, 'message': '获取商品信息失败'}


# 在goodslist页面添加商品
@app.route('/api/add_goods', methods=["POST"])
@login_required
def add_goods_api():
    goods_name = request.values.get("goods_name", "").strip()
    price = request.values.get("price", "").strip()
    category_id = request.values.get("category_id", "")
    new_category_name = request.values.get("new_category_name", "").strip()
    
    if not goods_name or not price:
        flash('商品名称和价格不能为空', 'error')
        return redirect(url_for('goodslist'))
    
    try:
        price = float(price)
        if price <= 0:
            flash('价格必须大于0', 'error')
            return redirect(url_for('goodslist'))
    except ValueError:
        flash('价格格式不正确', 'error')
        return redirect(url_for('goodslist'))
    
    try:
        # 如果选择了新建类别
        if category_id == 'new' and new_category_name:
            # 检查类别名是否已存在
            check_sql = "SELECT id FROM categories WHERE name = %s"
            cursor.execute(check_sql, (new_category_name,))
            existing_category = cursor.fetchone()
            
            if existing_category:
                category_id = existing_category[0]
                flash(f'类别 "{new_category_name}" 已存在，商品已添加到该类别', 'info')
            else:
                # 创建新类别
                create_category_sql = "INSERT INTO categories(name) VALUES(%s)"
                cursor.execute(create_category_sql, (new_category_name,))
                category_id = cursor.lastrowid
                flash(f'新类别 "{new_category_name}" 创建成功！', 'success')
        
        # 添加商品
        sql = "INSERT INTO goods_list(goods_name, price, category_id) VALUES(%s, %s, %s)"
        cursor.execute(sql, (goods_name, price, category_id if category_id and category_id != 'new' else None))
        db.commit()
        flash('商品添加成功！', 'success')
    except Exception as e:
        db.rollback()
        flash('添加商品时发生错误', 'error')
        print(f"Add goods error: {e}")
    
    return redirect(url_for('goodslist'))


@app.route('/orderlist', methods=["GET", "POST"])
@app.route('/orderlist/<int:page>', methods=["GET", "POST"])
@app.route('/orderlist/category/<int:category_id>', methods=["GET", "POST"])
@app.route('/orderlist/category/<int:category_id>/<int:page>', methods=["GET", "POST"])
@login_required
def orderlist(page=1, category_id=None):
    # 获取分页参数
    per_page = 10  # 每页显示10个商品
    offset = (page - 1) * per_page
    
    # 获取搜索关键词
    search_keyword = request.args.get('search', '').strip()
    
    # 获取所有类别用于下拉框
    categories_sql = "SELECT id, name FROM categories ORDER BY name"
    cursor.execute(categories_sql)
    categories = cursor.fetchall()
    
    # 构建查询条件
    where_conditions = []
    query_params = []
    
    # 添加类别筛选条件
    if category_id:
        where_conditions.append("category_id = %s")
        query_params.append(category_id)
    
    # 添加搜索条件
    if search_keyword:
        where_conditions.append("goods_name LIKE %s")
        query_params.append(f"%{search_keyword}%")
    
    # 构建WHERE子句
    where_clause = ""
    if where_conditions:
        where_clause = "WHERE " + " AND ".join(where_conditions)
    
    # 获取商品总数
    count_sql = f"SELECT COUNT(*) FROM goods_list {where_clause}"
    cursor.execute(count_sql, tuple(query_params))
    total_count = cursor.fetchone()[0]
    
    # 获取商品数据 - 使用简化查询
    goods_sql_simple = f"""
    SELECT id, goods_name, price, category_id
    FROM goods_list 
    {where_clause}
    LIMIT %s OFFSET %s
    """
    cursor.execute(goods_sql_simple, tuple(query_params + [per_page, offset]))
    simple_result = cursor.fetchall()
    
    # 手动构建最终结果
    if simple_result:
        goods_list_manual = []
        for item in simple_result:
            # 获取每个商品的类别名称
            category_name_sql = "SELECT name FROM categories WHERE id = %s"
            cursor.execute(category_name_sql, (item[3],))
            category_name_result = cursor.fetchone()
            category_name = category_name_result[0] if category_name_result else "未分类"
            
            # (id, goods_name, price, category_name, category_id)
            goods_list_manual.append((item[0], item[1], item[2], category_name, item[3]))
        
        goods_list = tuple(goods_list_manual)
    else:
        goods_list = ()
    
    # 设置当前类别名称
    if category_id:
        current_category_sql = "SELECT name FROM categories WHERE id = %s"
        cursor.execute(current_category_sql, (category_id,))
        current_category = cursor.fetchone()
        current_category_name = current_category[0] if current_category else "未知类别"
    else:
        current_category_name = "全部"
    
    # 计算总页数
    total_pages = (total_count + per_page - 1) // per_page
    
    # 计算分页信息
    has_prev = page > 1
    has_next = page < total_pages
    prev_page = page - 1 if has_prev else None
    next_page = page + 1 if has_next else None
    
    # 计算显示的页码范围
    start_page = max(1, page - 2)
    end_page = min(total_pages, page + 2)
    page_range = list(range(start_page, end_page + 1))
    
    # 计算当前显示的记录范围
    start_record = offset + 1 if goods_list else 0
    end_record = min(offset + per_page, total_count)
    
    pagination_info = {
        'page': page,
        'total_pages': total_pages,
        'total_count': total_count,
        'per_page': per_page,
        'has_prev': has_prev,
        'has_next': has_next,
        'prev_page': prev_page,
        'next_page': next_page,
        'page_range': page_range,
        'start_record': start_record,
        'end_record': end_record
    }
    if request.method == 'POST':
        # typelist=request.values.get("sale_name"," ")
        typelist = request.form.get('name')
        buy_name = request.values.get("buy_name", " ")
        print(typelist)
        #在这里定义即将要填到表格中的数据列表
        name_list=[]
        number_list=[]
        price_list=[]
        signal_price_list=[]
        for index in range(1, len(goods_list) + 1):
            if request.form.get(f'product_{index}'):  # 检查复选框是否被选中
                product_name = request.form.get(f'product_{index}')
                quantity = request.form.get(f'quantity_{index}')
                price = request.form.get(f'price_{index}')
                name_list.append(product_name)
                number_list.append(quantity)
                price_list.append(price)
                signal_price_list.append(float(quantity)*float(price))
                print(product_name, quantity, price)
        print(name_list,number_list,price_list)
        print(signal_price_list)

        # 下面是生成pdf的代码
        # 注册中文字体
        pdfmetrics.registerFont(TTFont('zw', 'STZHONGS.TTF'))  # 'zw'是您选择的字体名，'STZHONGS.TTF'是字体文件
        # 创建PDF文档
        pdf_buffer = BytesIO()
        pdf = SimpleDocTemplate(pdf_buffer, pagesize=A4)
        # pdf = SimpleDocTemplate("bill_with_borders.pdf", pagesize=A4)
        elements = []

        # 表格数据
        data = [
            [typelist, "商品名称", "数量", "单价（元）", "小计（元）"],
            ["单号：XSD0012312060002", "销售单", 1000, 85,"销售单"],
            ["客户：" + str(buy_name), 100, 100, 1280,"销售日期：" + datetime.datetime.now().strftime('%Y-%m-%d  %H:%M:%S'),128000],
            ["编号：", "产品名称", "总数量", "单价", "金额", "送货数量", "备注", ],
        ]
        #添加用户选中的数据
        #定义编号
        bianhao=1
        for i in range(len(name_list)):
            data.append([bianhao,name_list[i],number_list[i],price_list[i],format(signal_price_list[i],'.2f')])
            bianhao+=1
        total_money=0
        for i in signal_price_list:
            total_money+=i
        # 添加最后两行
        data.append(["总计", "", "", "", str(format(total_money,'.2f'))+"元"])
        data.append(["订货电话：19805893116", "", "", "总计", ""])
        #设置表格的高
        row_heights=[11 * mm]
        data_length=len(name_list)
        for i in range(data_length+5):
            row_heights.append(7 * mm)
        # 创建表格实例  这里的高度设置要根据用户勾选的数量来决定，所以这里还需要一个变量
        table = Table(data, colWidths=[20 * mm, 80 * mm, 20 * mm, 20 * mm, 20 * mm], rowHeights=row_heights)
        # 添加表格样式
        style = TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), 'zw'),  # 使用注册的中文字体
            ('BORDER', (0, 0), (-1, -1), 1, colors.black),  # 边框颜色和粗细
            ('GRID', (0, 0), (-1, -1), 1, colors.black),  # 网格线
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),  # 左右居中对齐
            ('VALIGN', (0, 0), (-1, 0), 'MIDDLE'),  # 居中对齐
            ('SPAN', (0, 0), (-1, 0)),  # 合并第一行的所有单元格来创建标题
            ('FONTSIZE',(0, 0), (-1, 0),25),    #调整第一行的字体大小
            ('LEADING', (0, 0), (-1, 0), 36),  # 第一行的文本行距
            # ('BACKGROUND', (0, 0), (-1, 0), colors.grey),  # 第一行背景色
            # ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),  # 第一行文字颜色
            ('SPAN', (0, 1), (3, 1)), #合并第二行前四列
            ('SPAN', (4, 1), (-1, 1)), #合并第二行后三列
            ('ALIGN', (0, 1), (3, 1), 'LEFT'),  # 二行前四列居中对齐
            ('ALIGN', (0, 2), (3, 2), 'LEFT'),  # 三行前四列居中对齐
            ('SPAN', (0, 2), (3, 2)),  # 合并第三行前四列
            ('SPAN', (4, 2), (-1, 2)),  # 合并第三行后三列
            ('BACKGROUND', (0, 3), (-1, 3), colors.grey),  # 第四行背景色
            ('SPAN', (0, -1), (3, -1)),  # 合并最后一行的前四列
            ('SPAN', (4, -1), (-1, -1)),  # 合并最后一行的后三列

            ('ALIGN', (0, -1), (3, -1), 'LEFT'),  # 最后一行的前四列居中对齐
            ('SPAN', (0, -2), (3, -2)),  # 合并倒数第二行的前四列

            # ('SPAN', (0, 4), (-3, 4)),  # 合并第五行的单元格，从第一个到最后一个单元格
        ])
        table.setStyle(style)
        # 将表格添加到PDF文档
        elements.append(table)
        # 生成PDF
        pdf.build(elements)
        # 重置文件指针到开始
        pdf_buffer.seek(0)
        # 创建一个生成PDF的HTTP响应
        response = make_response(pdf_buffer.read())
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = 'inline; filename=bill.pdf'
        return response

    return render_template('orderlist.html', 
                         goods_list=goods_list, 
                         sale_name=sale_name, 
                         pagination=pagination_info,
                         categories=categories,
                         current_category_id=category_id,
                         current_category_name=current_category_name,
                         search_keyword=search_keyword)


# 类别管理API

# 获取所有类别
@app.route('/api/categories', methods=['GET'])
@login_required
def get_categories():
    try:
        sql = """
        SELECT c.id, c.name, c.description, c.created_at, COUNT(g.id) as goods_count
        FROM categories c 
        LEFT JOIN goods_list g ON c.id = g.category_id 
        GROUP BY c.id, c.name, c.description, c.created_at
        ORDER BY c.name
        """
        cursor.execute(sql)
        categories = cursor.fetchall()
        
        category_list = []
        for category in categories:
            category_list.append({
                'id': category[0],
                'name': category[1],
                'description': category[2],
                'created_at': category[3].strftime('%Y-%m-%d %H:%M:%S') if category[3] else '',
                'goods_count': category[4]
            })
        
        return {
            'success': True,
            'categories': category_list
        }
    except Exception as e:
        print(f"Get categories error: {e}")
        return {'success': False, 'message': '获取类别列表失败'}

# 更新类别
@app.route('/api/categories/<int:category_id>', methods=['PUT'])
@login_required
def update_category(category_id):
    try:
        category_name = request.form.get('category_name', '').strip()
        description = request.form.get('description', '').strip()
        
        if not category_name:
            return {'success': False, 'message': '类别名称不能为空'}
        
        # 检查名称是否与其他类别重复
        check_sql = "SELECT id FROM categories WHERE name = %s AND id != %s"
        cursor.execute(check_sql, (category_name, category_id))
        existing = cursor.fetchone()
        
        if existing:
            return {'success': False, 'message': '类别名称已存在'}
        
        # 更新类别
        sql = "UPDATE categories SET name = %s, description = %s WHERE id = %s"
        cursor.execute(sql, (category_name, description, category_id))
        db.commit()
        
        if cursor.rowcount > 0:
            return {'success': True, 'message': '类别更新成功'}
        else:
            return {'success': False, 'message': '类别不存在'}
            
    except Exception as e:
        db.rollback()
        print(f"Update category error: {e}")
        return {'success': False, 'message': '更新类别失败'}

# 删除类别
@app.route('/api/categories/<int:category_id>', methods=['DELETE'])
@login_required
def delete_category(category_id):
    try:
        # 先获取类别信息和商品数量
        info_sql = """
        SELECT c.name, COUNT(g.id) as goods_count
        FROM categories c 
        LEFT JOIN goods_list g ON c.id = g.category_id 
        WHERE c.id = %s
        GROUP BY c.id, c.name
        """
        cursor.execute(info_sql, (category_id,))
        category_info = cursor.fetchone()
        
        if not category_info:
            return {'success': False, 'message': '类别不存在'}
        
        category_name, goods_count = category_info
        
        # 删除该类别下的所有商品
        if goods_count > 0:
            delete_goods_sql = "DELETE FROM goods_list WHERE category_id = %s"
            cursor.execute(delete_goods_sql, (category_id,))
        
        # 删除类别
        delete_category_sql = "DELETE FROM categories WHERE id = %s"
        cursor.execute(delete_category_sql, (category_id,))
        
        db.commit()
        
        if goods_count > 0:
            message = f'类别 "{category_name}" 及其下 {goods_count} 个商品已删除'
        else:
            message = f'类别 "{category_name}" 已删除'
        
        return {'success': True, 'message': message}
        
    except Exception as e:
        db.rollback()
        print(f"Delete category error: {e}")
        return {'success': False, 'message': '删除类别失败'}


if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5555, debug=True)
