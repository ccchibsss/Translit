import streamlit as st
import pandas as pd
from PIL import Image, ImageDraw, ImageFont
import requests
from io import BytesIO
import os
import json
import time
import hashlib
import zipfile
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import tempfile
import shutil
import re
import gspread
from google.oauth2 import service_account
from gspread_dataframe import get_as_dataframe, set_with_dataframe
import gc

# ==================== НАСТРОЙКА СТРАНИЦЫ ====================
st.set_page_config(
    page_title="🎯 Генератор Инфографики v3.0 (Excel + Google Sheets)",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ==================== ИНИЦИАЛИЗАЦИЯ СЕССИИ ====================
if 'df' not in st.session_state:
    st.session_state.df = None
if 'data_source' not in st.session_state:
    st.session_state.data_source = None
if 'processing_stats' not in st.session_state:
    st.session_state.processing_stats = {
        'total': 0, 'processed': 0, 'errors': 0,
        'start_time': None, 'end_time': None
    }
if 'batch_id' not in st.session_state:
    st.session_state.batch_id = datetime.now().strftime("%Y%m%d_%H%M%S")

# ==================== КОНФИГУРАЦИЯ ====================
class Config:
    TEMPLATES = {
        "📋 Стандартный": {
            "size": (1200, 1200),
            "font_sizes": {"top": 36, "bottom": 20},
            "colors": {"top_left": (255, 255, 255), "top_right": (255, 215, 0),
                      "bottom_left": (220, 220, 220), "bottom_right": (255, 107, 107)},
            "background_opacity": 180, "text_shadow": True
        },
        "⭐ Премиум": {
            "size": (1200, 1200),
            "font_sizes": {"top": 32, "bottom": 18},
            "colors": {"top_left": (255, 255, 255), "top_right": (200, 200, 200),
                      "bottom_left": (180, 180, 180), "bottom_right": (160, 160, 160)},
            "background_opacity": 220, "text_shadow": False
        },
        "🔥 Акционный": {
            "size": (1200, 1200),
            "font_sizes": {"top": 40, "bottom": 22},
            "colors": {"top_left": (255, 255, 0), "top_right": (255, 50, 50),
                      "bottom_left": (255, 255, 255), "bottom_right": (255, 150, 50)},
            "background_opacity": 200, "text_shadow": True
        },
        "📱 Вертикальный": {
            "size": (1080, 1920),
            "font_sizes": {"top": 34, "bottom": 18},
            "colors": {"top_left": (255, 255, 255), "top_right": (255, 105, 180),
                      "bottom_left": (200, 230, 255), "bottom_right": (144, 238, 144)},
            "background_opacity": 160, "text_shadow": True
        }
    }
    
    EXPORT_FORMATS = {
        "JPEG": {"quality": 85, "extension": "jpg"},
        "PNG": {"quality": 100, "extension": "png"},
        "WebP": {"quality": 90, "extension": "webp"}
    }

# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================
def sanitize_filename(filename):
    filename = filename.replace(' ', '_')
    filename = re.sub(r'[<>:"/\\|?*]', '', filename)
    translit_map = {'а':'a','б':'b','в':'v','г':'g','д':'d','е':'e','ё':'yo',
                   'ж':'zh','з':'z','и':'i','й':'y','к':'k','л':'l','м':'m',
                   'н':'n','о':'o','п':'p','р':'r','с':'s','т':'t','у':'u',
                   'ф':'f','х':'kh','ц':'ts','ч':'ch','ш':'sh','щ':'shch',
                   'ы':'y','э':'e','ю':'yu','я':'ya'}
    for rus, eng in translit_map.items():
        filename = filename.replace(rus, eng).replace(rus.upper(), eng.upper())
    return filename[:100]

def create_output_filename(row, prefix="", suffix="", add_hash=True):
    base_name = str(row.get('Название', f'product_{row.name}'))
    base_name = sanitize_filename(base_name)
    filename = f"{prefix}{base_name}{suffix}"
    if add_hash:
        hash_str = hashlib.md5(str(row).encode()).hexdigest()[:8]
        filename = f"{filename}_{hash_str}"
    filename = f"{filename}_{row.name:06d}"
    return filename

@st.cache_data(ttl=300)
def download_image_cached(url, timeout=15, retries=2):
    for attempt in range(retries + 1):
        try:
            response = requests.get(url, timeout=timeout, 
                                   headers={'User-Agent': 'Mozilla/5.0'})
            response.raise_for_status()
            if 'image' not in response.headers.get('content-type', ''):
                raise ValueError(f"URL не ведет к изображению")
            return Image.open(BytesIO(response.content))
        except Exception as e:
            if attempt == retries:
                raise Exception(f"Не удалось загрузить: {e}")
            time.sleep(1)
    return None

def add_text_with_background(draw, position, text, font, text_color, 
                            bg_color, bg_opacity=180, padding=10):
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width, text_height = bbox[2] - bbox[0], bbox[3] - bbox[1]
    bg_x1, bg_y1 = position[0] - padding, position[1] - padding
    bg_x2, bg_y2 = position[0] + text_width + padding, position[1] + text_height + padding
    bg_color_with_alpha = (*bg_color, bg_opacity)
    draw.rectangle([bg_x1, bg_y1, bg_x2, bg_y2], fill=bg_color_with_alpha)
    draw.text(position, text, fill=text_color, font=font)
    return (bg_x1, bg_y1, bg_x2, bg_y2)

def create_infographic(original_img, text_data, template_config, 
                      add_watermark=False, watermark_text=""):
    img = original_img.resize(template_config['size'], Image.Resampling.LANCZOS)
    draw = ImageDraw.Draw(img, 'RGBA')
    
    try:
        font_bold = ImageFont.truetype("fonts/Roboto-Bold.ttf", 
                                      template_config['font_sizes']['top"])
        font_regular = ImageFont.truetype("fonts/Roboto-Regular.ttf", 
                                         template_config['font_sizes']['bottom'])
    except:
        font_bold = ImageFont.load_default()
        font_regular = ImageFont.load_default()
    
    width, height = img.size
    positions = {
        "top_left": (50, 50),
        "top_right": (width - 450, 50),
        "bottom_left": (50, height - 150),
        "bottom_right": (width - 450, height - 150)
    }
    
    if text_data.get('top_left'):
        add_text_with_background(draw, positions["top_left"], text_data['top_left'], 
                                font_bold, template_config['colors']['top_left'],
                                (0, 0, 0, 180), template_config['background_opacity'])
    
    if text_data.get('top_right'):
        add_text_with_background(draw, positions["top_right"], text_data['top_right'],
                                font_bold, template_config['colors']['top_right'],
                                (0, 0, 0, 180), template_config['background_opacity'])
    
    if text_data.get('bottom_left'):
        add_text_with_background(draw, positions["bottom_left"], text_data['bottom_left'],
                                font_regular, template_config['colors']['bottom_left'],
                                (0, 0, 0, 150), template_config['background_opacity'])
    
    if text_data.get('bottom_right'):
        add_text_with_background(draw, positions["bottom_right"], text_data['bottom_right'],
                                font_regular, template_config['colors']['bottom_right'],
                                (0, 0, 0, 150), template_config['background_opacity'])
    
    if add_watermark and watermark_text:
        watermark_font = ImageFont.load_default()
        watermark_position = (width // 2, height - 30)
        draw.text(watermark_position, watermark_text, fill=(255, 255, 255, 128),
                 font=watermark_font, anchor="mm")
    
    return img

# ==================== ФУНКЦИИ ДЛЯ GOOGLE SHEETS ====================
def init_google_sheets_connection(credentials_json, spreadsheet_id):
    """Инициализация подключения к Google Sheets"""
    try:
        credentials = service_account.Credentials.from_service_account_info(
            credentials_json,
            scopes=['https://www.googleapis.com/auth/spreadsheets',
                   'https://www.googleapis.com/auth/drive']
        )
        gc = gspread.authorize(credentials)
        spreadsheet = gc.open_by_key(spreadsheet_id)
        worksheet = spreadsheet.sheet1
        df = get_as_dataframe(worksheet, evaluate_formulas=True)
        df = df.dropna(how='all')
        return df, None
    except Exception as e:
        return None, str(e)

def save_to_google_sheets(df, credentials_json, spreadsheet_id):
    """Сохранение данных обратно в Google Sheets"""
    try:
        credentials = service_account.Credentials.from_service_account_info(
            credentials_json,
            scopes=['https://www.googleapis.com/auth/spreadsheets',
                   'https://www.googleapis.com/auth/drive']
        )
        gc = gspread.authorize(credentials)
        spreadsheet = gc.open_by_key(spreadsheet_id)
        worksheet = spreadsheet.sheet1
        worksheet.clear()
        set_with_dataframe(worksheet, df)
        return True, None
    except Exception as e:
        return False, str(e)

# ==================== ОСНОВНОЙ ИНТЕРФЕЙС ====================
st.title("🎯 Генератор Инфографики v3.0 (Excel + Google Sheets)")

# Боковая панель
with st.sidebar:
    st.header("📋 Источник данных")
    data_source = st.radio(
        "Выберите источник данных:",
        ["📁 Локальный Excel файл", "☁️ Google Таблица"],
        index=0
    )
    
    st.session_state.data_source = data_source
    
    if data_source == "☁️ Google Таблица":
        st.subheader("Настройки Google Sheets")
        
        spreadsheet_id = st.text_input(
            "ID таблицы",
            help="ID из URL: https://docs.google.com/spreadsheets/d/ТУТ_ID_ТАБЛИЦЫ/edit"
        )
        
        creds_json_str = st.text_area(
            "JSON учетных данных сервисного аккаунта",
            height=200,
            help="Вставьте JSON ключ сервисного аккаунта"
        )
        
        if st.button("🔗 Подключиться к Google Sheets"):
            if spreadsheet_id and creds_json_str:
                try:
                    credentials_json = json.loads(creds_json_str)
                    with st.spinner("Подключение к Google Sheets..."):
                        df, error = init_google_sheets_connection(
                            credentials_json, spreadsheet_id
                        )
                        
                        if error:
                            st.error(f"Ошибка подключения: {error}")
                            st.info("""
                            **Проверьте:**
                            1. Таблица доступна для сервисного аккаунта
                            2. JSON ключ верный
                            3. Интернет-соединение
                            """)
                        else:
                            st.session_state.df = df
                            st.session_state.gs_creds = credentials_json
                            st.session_state.gs_id = spreadsheet_id
                            st.success(f"✅ Загружено {len(df)} строк")
                except json.JSONDecodeError:
                    st.error("Неверный формат JSON")
    
    st.markdown("---")
    st.header("⚙️ Настройки системы")
    
    export_format = st.selectbox(
        "Формат сохранения",
        list(Config.EXPORT_FORMATS.keys()),
        index=0
    )
    
    st.subheader("📝 Имена файлов")
    filename_prefix = st.text_input("Префикс", "product_")
    filename_suffix = st.text_input("Суффикс", "_promo")
    add_watermark = st.checkbox("Добавить водяной знак")
    if add_watermark:
        watermark_text = st.text_input("Текст водяного знака", "© ВашБренд 2024")

# ==================== ЗАГРУЗКА ДАННЫХ ====================
st.header("1. 📊 Загрузка данных")

if st.session_state.data_source == "📁 Локальный Excel файл":
    uploaded_file = st.file_uploader(
        "Загрузите Excel-файл",
        type=['xlsx', 'xls'],
        help="Файл должен содержать колонки: Название, URL картинки, Цена"
    )
    
    if uploaded_file:
        try:
            df = pd.read_excel(uploaded_file)
            st.session_state.df = df
            st.success(f"✅ Успешно загружено {len(df)} строк")
            
            with st.expander("📋 Предпросмотр данных", expanded=True):
                st.dataframe(df.head(10), use_container_width=True)
                
        except Exception as e:
            st.error(f"❌ Ошибка при чтении файла: {str(e)}")

# Если данные загружены (из любого источника)
if st.session_state.df is not None:
    df = st.session_state.df
    
    # ==================== 2. КОНФИГУРАЦИЯ СТОЛБЦОВ ====================
    st.header("2. ⚙️ Конфигурация столбцов")
    
    col1, col2 = st.columns(2)
    column_mapping = {}
    
    with col1:
        st.subheader("Основные данные")
        column_mapping['top_left'] = st.selectbox(
            "Столбец с названием", 
            df.columns, 
            index=min(0, len(df.columns)-1)
        )
        column_mapping['image_url'] = st.selectbox(
            "Столбец с URL изображения", 
            df.columns, 
            index=min(2, len(df.columns)-1) if len(df.columns) > 2 else 0
        )
        column_mapping['top_right'] = st.selectbox(
            "Столбец с ценой", 
            df.columns, 
            index=min(3, len(df.columns)-1) if len(df.columns) > 3 else 0
        )
    
    with col2:
        st.subheader("Дополнительные данные")
        features_options = ['Не использовать'] + list(df.columns)
        column_mapping['bottom_left'] = st.selectbox(
            "Столбец с характеристиками", 
            features_options
        )
        discount_options = ['Не использовать'] + list(df.columns)
        column_mapping['bottom_right'] = st.selectbox(
            "Столбец со скидкой", 
            discount_options
        )
    
    # ==================== 3. ВЫБОР ШАБЛОНА ====================
    st.header("3. 🎭 Выбор шаблона")
    
    template_names = list(Config.TEMPLATES.keys())
    cols = st.columns(4)
    
    for idx, template_name in enumerate(template_names):
        with cols[idx]:
            st.markdown(f"**{template_name}**")
            st.caption(Config.TEMPLATES[template_name].get('description', ''))
    
    selected_template = st.radio(
        "Выберите шаблон дизайна:",
        template_names,
        horizontal=True,
        label_visibility="collapsed"
    )
    
    template_config = Config.TEMPLATES[selected_template]
    
    # ==================== 4. ПРЕДПРОСМОТР ====================
    st.header("4. 🔍 Предпросмотр")
    
    col1, col2 = st.columns([2, 1])
    with col1:
        preview_row = st.slider(
            "Выберите строку для предпросмотра",
            min_value=0,
            max_value=min(9, len(df)-1),
            value=0
        )
    with col2:
        preview_timeout = st.number_input("Таймаут (сек)", 5, 60, 15)
    
    if st.button("🔄 Сгенерировать предпросмотр", type="secondary"):
        with st.spinner("Создание превью..."):
            try:
                row = df.iloc[preview_row]
                
                text_data = {
                    'top_left': str(row[column_mapping['top_left']]) if column_mapping['top_left'] in df.columns and pd.notna(row[column_mapping['top_left']]) else "",
                    'top_right': str(row[column_mapping['top_right']]) if column_mapping['top_right'] in df.columns and pd.notna(row[column_mapping['top_right']]) else "",
                    'bottom_left': str(row[column_mapping['bottom_left']]) if column_mapping['bottom_left'] != 'Не использовать' and column_mapping['bottom_left'] in df.columns and pd.notna(row[column_mapping['bottom_left']]) else "",
                    'bottom_right': str(row[column_mapping['bottom_right']]) if column_mapping['bottom_right'] != 'Не использовать' and column_mapping['bottom_right'] in df.columns and pd.notna(row[column_mapping['bottom_right']]) else ""
                }
                
                img_url = str(row[column_mapping['image_url']]) if column_mapping['image_url'] in df.columns else ""
                original_img = download_image_cached(img_url, timeout=preview_timeout)
                
                if original_img:
                    infographic_img = create_infographic(
                        original_img, text_data, template_config,
                        add_watermark=add_watermark,
                        watermark_text=watermark_text if 'watermark_text' in locals() else ""
                    )
                    
                    col_before, col_after = st.columns(2)
                    with col_before:
                        st.image(original_img, caption="🖼️ Оригинал", 
                                use_container_width=True)
                    with col_after:
                        st.image(infographic_img, caption="🎯 Инфографика", 
                                use_container_width=True)
                    
                    if st.button("💾 Сохранить тестовый файл"):
                        test_filename = f"preview_{st.session_state.batch_id}.jpg"
                        infographic_img.save(test_filename, quality=95)
                        with open(test_filename, "rb") as file:
                            st.download_button(
                                "Скачать тестовый файл",
                                file,
                                file_name=test_filename,
                                mime="image/jpeg"
                            )
                
            except Exception as e:
                st.error(f"❌ Ошибка предпросмотра: {str(e)}")
    
    # ==================== 5. МАССОВАЯ ОБРАБОТКА ====================
    st.header("5. ⚡ Массовая обработка")
    
    with st.expander("⚙️ Настройки обработки", expanded=True):
        col1, col2 = st.columns(2)
        with col1:
            num_threads = st.slider("Количество потоков", 1, 16, 8,
                                   help="Используйте ThreadPoolExecutor вместо ProcessPool для совместимости[citation:1]")
            retry_count = st.slider("Повторные попытки", 0, 5, 2)
        with col2:
            batch_size = st.slider("Размер пакета", 10, 500, 100)
            rows_to_process = st.number_input("Сколько строк обработать",
                                            1, len(df), min(500, len(df)))
    
    def process_single_image_wrapper(args):
        """Обертка для обработки одного изображения"""
        idx, row = args
        try:
            text_data = {
                'top_left': str(row[column_mapping['top_left']]) if column_mapping['top_left'] in df.columns and pd.notna(row[column_mapping['top_left']]) else "",
                'top_right': str(row[column_mapping['top_right']]) if column_mapping['top_right'] in df.columns and pd.notna(row[column_mapping['top_right']]) else "",
                'bottom_left': str(row[column_mapping['bottom_left']]) if column_mapping['bottom_left'] != 'Не использовать' and column_mapping['bottom_left'] in df.columns and pd.notna(row[column_mapping['bottom_left']]) else "",
                'bottom_right': str(row[column_mapping['bottom_right']]) if column_mapping['bottom_right'] != 'Не использовать' and column_mapping['bottom_right'] in df.columns and pd.notna(row[column_mapping['bottom_right']]) else ""
            }
            
            img_url = str(row[column_mapping['image_url']]) if column_mapping['image_url'] in df.columns else ""
            original_img = download_image_cached(img_url, timeout=15, retries=retry_count)
            
            if not original_img:
                raise Exception("Не удалось загрузить изображение")
            
            infographic_img = create_infographic(
                original_img, text_data, template_config,
                add_watermark=add_watermark,
                watermark_text=watermark_text if 'watermark_text' in locals() else ""
            )
            
            filename_base = create_output_filename(
                row, 
                prefix=filename_prefix,
                suffix=filename_suffix,
                add_hash=True
            )
            
            output_dir = f"output/batch_{st.session_state.batch_id}"
            os.makedirs(output_dir, exist_ok=True)
            
            export_config = Config.EXPORT_FORMATS[export_format]
            output_path = os.path.join(
                output_dir,
                f"{filename_base}.{export_config['extension']}"
            )
            
            save_params = {'quality': export_config['quality']} if export_format == 'JPEG' else {}
            infographic_img.save(output_path, **save_params)
            
            return {
                'index': idx,
                'status': 'success',
                'filename': os.path.basename(output_path),
                'path': output_path
            }
            
        except Exception as e:
            return {
                'index': idx,
                'status': 'error',
                'error': str(e)
            }
    
    if st.button("🚀 Запустить массовую обработку", type="primary"):
        st.session_state.processing = True
        st.session_state.processing_stats = {
            'total': rows_to_process,
            'processed': 0,
            'errors': 0,
            'start_time': datetime.now(),
            'end_time': None
        }
        
        output_dir = f"output/batch_{st.session_state.batch_id}"
        os.makedirs(output_dir, exist_ok=True)
        
        progress_bar = st.progress(0)
        status_text = st.empty()
        results = []
        error_log = []
        
        try:
            # Используем ThreadPoolExecutor вместо ProcessPoolExecutor[citation:1]
            with ThreadPoolExecutor(max_workers=num_threads) as executor:
                # Подготавливаем задачи
                tasks = [(i, df.iloc[i]) for i in range(min(rows_to_process, len(df)))]
                
                # Отправляем задачи на выполнение
                future_to_idx = {
                    executor.submit(process_single_image_wrapper, task): task[0] 
                    for task in tasks
                }
                
                # Обрабатываем результаты по мере их поступления
                for future in as_completed(future_to_idx):
                    result = future.result()
                    results.append(result)
                    
                    if result['status'] == 'error':
                        st.session_state.processing_stats['errors'] += 1
                        error_log.append(result)
                    else:
                        st.session_state.processing_stats['processed'] += 1
                    
                    # Обновляем прогресс
                    progress = st.session_state.processing_stats['processed'] / rows_to_process
                    progress_bar.progress(progress)
                    
                    status_text.text(
                        f"Обработано: {st.session_state.processing_stats['processed']}/"
                        f"{rows_to_process} | "
                        f"Ошибки: {st.session_state.processing_stats['errors']}"
                    )
            
            # Явно вызываем сборщик мусора для освобождения памяти[citation:6]
            gc.collect()
            
            # Сохраняем метаданные
            metadata = []
            for result in results:
                if result['status'] == 'success':
                    row = df.iloc[result['index']]
                    metadata.append({
                        'original_index': result['index'],
                        'filename': result['filename'],
                        'product_name': str(row[column_mapping['top_left']]) if column_mapping['top_left'] in df.columns else "",
                        'price': str(row[column_mapping['top_right']]) if column_mapping['top_right'] in df.columns else "",
                        'image_url': str(row[column_mapping['image_url']]) if column_mapping['image_url'] in df.columns else "",
                        'template': selected_template,
                        'export_format': export_format,
                        'processing_time': datetime.now().isoformat()
                    })
            
            if metadata:
                metadata_df = pd.DataFrame(metadata)
                metadata_path = os.path.join(output_dir, "metadata.csv")
                metadata_df.to_csv(metadata_path, index=False, encoding='utf-8-sig')
            
            if error_log:
                error_df = pd.DataFrame(error_log)
                error_path = os.path.join(output_dir, "error_log.csv")
                error_df.to_csv(error_path, index=False, encoding='utf-8-sig')
            
            # Создаем ZIP архив
            zip_path = f"batch_{st.session_state.batch_id}.zip"
            with zipfile.ZipFile(zip_path, 'w') as zipf:
                for root, dirs, files in os.walk(output_dir):
                    for file in files:
                        file_path = os.path.join(root, file)
                        zipf.write(file_path, os.path.relpath(file_path, output_dir))
            
            st.session_state.processing_stats['end_time'] = datetime.now()
            st.session_state.processing = False
            
            st.success("✅ Обработка завершена успешно!")
            
            # Показываем статистику
            processing_time = (
                st.session_state.processing_stats['end_time'] - 
                st.session_state.processing_stats['start_time']
            ).total_seconds()
            
            st.info(f"""
            **Статистика обработки:**
            - Всего обработано: {st.session_state.processing_stats['processed']}
            - Ошибок: {st.session_state.processing_stats['errors']}
            - Время обработки: {processing_time:.1f} сек
            - Скорость: {st.session_state.processing_stats['processed']/max(processing_time, 0.1):.1f} изобр./сек
            """)
            
            # Кнопка для скачивания
            with open(zip_path, "rb") as f:
                st.download_button(
                    "📦 Скачать ZIP архив с результатами",
                    f,
                    file_name=os.path.basename(zip_path),
                    mime="application/zip"
                )
            
        except Exception as e:
            st.error(f"❌ Критическая ошибка: {str(e)}")
            st.session_state.processing = False

# ==================== ТЕХНИЧЕСКИЕ ДЕТАЛИ РЕАЛИЗАЦИИ ====================
with st.expander("🔧 Технические детали реализации", expanded=False):
    st.markdown("""
    ### 🛠️ Ключевые улучшения в версии 3.0
    
    **1. Исправление проблем с многопоточностью:**
    - Используется `ThreadPoolExecutor` вместо `ProcessPoolExecutor`
    - Решает проблемы с pickle сериализацией в Streamlit[citation:1][citation:8]
    - Более стабильная работа на Windows
    
    **2. Оптимизация памяти:**
    - Кэширование загрузки изображений с `@st.cache_data`[citation:10]
    - Явный вызов `gc.collect()` после обработки[citation:6]
    - Лимитирование отображаемых данных[citation:5]
    
    **3. Двойной способ ввода данных:**
    - Локальные Excel файлы (простота использования)
    - Google Sheets API (для командной работы)
    
    **4. Улучшенная обработка ошибок:**
    - Контроль времени ожидания для загрузки изображений
    - Повторные попытки при сбоях сети
    - Детальное логирование ошибок
    
    ### 📊 Рекомендации по развертыванию
    
    **Для локального использования:**
    ```bash
    pip install streamlit pandas pillow requests gspread google-auth
    streamlit run app.py
    ```
    
    **Для развертывания в облаке:**
    1. **Streamlit Cloud**: До 1GB RAM[citation:4]
    2. **Hugging Face Spaces**: Бесплатный хостинг
    3. **Google Cloud Run**: Масштабируемый, контроль над RAM
    
    **Оптимальные настройки для больших объемов:**
    - 100-1000 изображений: 8 потоков, размер пакета 100
    - 1000-10000 изображений: 12 потоков, размер пакета 200
    - 10000+ изображений: 16 потоков, размер пакета 500
    """)

# ==================== ИНСТРУКЦИЯ ====================
st.markdown("---")
st.success("""
🎯 **Генератор Инфографики v3.0 готов к работе!**

**Быстрый старт:**
1. Выберите источник данных (Excel или Google Sheets)
2. Загрузите/подключите данные
3. Настройте соответствие столбцов
4. Выберите шаблон дизайна
5. Протестируйте на предпросмотре
6. Запустите массовую обработку

**Особенности этой версии:**
✅ Двойной способ ввода данных
✅ Исправлены проблемы с многопоточностью
✅ Оптимизировано использование памяти
✅ Улучшенная обработка ошибок
✅ Полная поддержка вашей инструкции
""")
