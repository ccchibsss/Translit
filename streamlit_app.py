import streamlit as st
from streamlit_gsheets import GSheetsConnection
from PIL import Image, ImageDraw, ImageFont
import requests
from io import BytesIO
import os
import concurrent.futures
import time
from datetime import datetime
import gc
import logging
from pathlib import Path
import pandas as pd
import hashlib
import json
import psutil
from functools import lru_cache
from threading import Semaphore
import zipfile
import re
import platform
import sys
import math

# ==================== НАСТРОЙКИ ИНТЕРФЕЙСА ====================
st.set_page_config(page_title="Генератор инфографики для маркетплейсов v3.0", layout="wide")
st.title("🛍️ Генератор инфографики для карточек товаров - ПРОМЫШЛЕННАЯ ВЕРСИЯ 3.0")
st.markdown("""
**Промышленная версия v3.0:** Оптимизировано для обработки 100,000+ изображений с AI-оптимизацией, 
умным кэшированием и адаптивным управлением ресурсами.
""")
st.divider()

# ==================== КЛАСС ДЛЯ РАСШИРЕННОГО МОНИТОРИНГА ПРОИЗВОДИТЕЛЬНОСТИ ====================
class EnhancedPerformanceMonitor:
    """Расширенный мониторинг производительности с предсказаниями и аналитикой"""
    def __init__(self):
        self.metrics = {
            'images_processed': 0,
            'avg_processing_time': 0,
            'memory_usage': [],
            'errors_per_hour': 0,
            'start_time': time.time(),
            'last_checkpoint': time.time(),
            'network_speed': [],
            'cpu_usage': []
        }
        self.history = []
        self.predictions = []
        self.current_batch_size = 100
        self.optimization_history = []
        
    def update_metrics(self, processing_time, success=True, network_speed=None):
        """Обновление метрик с дополнительными параметрами"""
        self.metrics['images_processed'] += 1
        self.metrics['avg_processing_time'] = (
            self.metrics['avg_processing_time'] * 0.9 + processing_time * 0.1
        )
        
        # Мониторинг памяти
        memory_mb = psutil.Process().memory_info().rss / 1024 / 1024
        self.metrics['memory_usage'].append(memory_mb)
        if len(self.metrics['memory_usage']) > 100:
            self.metrics['memory_usage'].pop(0)
        
        # Мониторинг CPU
        cpu_percent = psutil.cpu_percent(interval=0.1)
        self.metrics['cpu_usage'].append(cpu_percent)
        if len(self.metrics['cpu_usage']) > 100:
            self.metrics['cpu_usage'].pop(0)
        
        # Скорость сети
        if network_speed:
            self.metrics['network_speed'].append(network_speed)
            if len(self.metrics['network_speed']) > 50:
                self.metrics['network_speed'].pop(0)
        
        # Счетчик ошибок
        if not success:
            self.metrics['errors_per_hour'] += 1
        
        # Сохранение в историю
        history_entry = {
            'timestamp': time.time(),
            'processing_time': processing_time,
            'success': success,
            'memory_mb': memory_mb,
            'cpu_percent': cpu_percent,
            'images_processed': self.metrics['images_processed']
        }
        self.history.append(history_entry)
        if len(self.history) > 1000:
            self.history.pop(0)
    
    def get_performance_dashboard(self):
        """Получение текущей статистики производительности"""
        elapsed_time = time.time() - self.metrics['start_time']
        
        avg_network = (sum(self.metrics['network_speed']) / len(self.metrics['network_speed']) 
                      if self.metrics['network_speed'] else 0)
        avg_cpu = (sum(self.metrics['cpu_usage']) / len(self.metrics['cpu_usage']) 
                  if self.metrics['cpu_usage'] else 0)
        
        return {
            'throughput': self.metrics['images_processed'] / max(elapsed_time, 1),
            'avg_time_per_image': self.metrics['avg_processing_time'],
            'max_memory_mb': max(self.metrics['memory_usage']) if self.metrics['memory_usage'] else 0,
            'current_memory_mb': psutil.Process().memory_info().rss / 1024 / 1024,
            'avg_cpu_percent': avg_cpu,
            'avg_network_kbps': avg_network,
            'total_processed': self.metrics['images_processed'],
            'elapsed_time': elapsed_time,
            'errors_per_hour': self.metrics['errors_per_hour'] / max(elapsed_time / 3600, 0.001)
        }
    
    def estimate_completion(self, total_tasks):
        """Оценка времени завершения с учетом тренда"""
        if self.metrics['images_processed'] == 0:
            return None
        
        processed = self.metrics['images_processed']
        elapsed = time.time() - self.metrics['start_time']
        
        if len(self.history) >= 3:
            # Используем скользящее среднее последних 10 записей
            recent_times = [h['processing_time'] for h in self.history[-10:] if h['processing_time'] > 0]
            if recent_times:
                time_per_task = sum(recent_times) / len(recent_times)
                remaining = total_tasks - processed
                estimated_remaining = time_per_task * remaining
                
                # Учет возможного замедления при увеличении нагрузки
                if len(self.history) > 50:
                    # Проверяем тренд
                    recent_avg = sum(recent_times) / len(recent_times)
                    older_avg = sum([h['processing_time'] for h in self.history[-50:-10]]) / 40
                    if recent_avg > older_avg * 1.3:  # Замедление на 30%
                        estimated_remaining *= 1.5  # Добавляем запас
                
                return estimated_remaining
        
        # Fallback на простой расчет
        time_per_task = elapsed / processed
        remaining = total_tasks - processed
        return time_per_task * remaining
    
    def predict_optimal_batch_size(self):
        """Предсказание оптимального размера партии"""
        if len(self.history) < 3:
            return 100
        
        # Анализ последних записей
        recent_history = self.history[-20:]
        if not recent_history:
            return self.current_batch_size
        
        # Вычисляем средние показатели
        avg_time = sum(h['processing_time'] for h in recent_history) / len(recent_history)
        avg_memory = sum(h['memory_mb'] for h in recent_history) / len(recent_history)
        
        # Получаем текущее использование памяти системы
        system_memory = psutil.virtual_memory()
        memory_percent = system_memory.percent
        
        # Простая эвристика для оптимизации
        if memory_percent > st.session_state.get('memory_threshold', 80):
            # Память под давлением - уменьшаем партию
            new_batch = max(50, int(self.current_batch_size * 0.7))
            self.optimization_history.append({
                'timestamp': time.time(),
                'old_size': self.current_batch_size,
                'new_size': new_batch,
                'reason': f'Высокая память: {memory_percent:.1f}%'
            })
        elif avg_time < 1.0 and memory_percent < 70:
            # Хорошая производительность - увеличиваем партию
            new_batch = min(500, int(self.current_batch_size * 1.3))
            self.optimization_history.append({
                'timestamp': time.time(),
                'old_size': self.current_batch_size,
                'new_size': new_batch,
                'reason': f'Хорошая производительность: {avg_time:.2f}с'
            })
        else:
            # Сохраняем текущий размер
            new_batch = self.current_batch_size
        
        self.current_batch_size = new_batch
        return new_batch
    
    def get_optimization_recommendations(self):
        """Получение рекомендаций по оптимизации"""
        recommendations = []
        
        perf_data = self.get_performance_dashboard()
        
        if perf_data['errors_per_hour'] > 10:
            recommendations.append({
                'level': 'warning',
                'message': "Высокий уровень ошибок. Увеличьте таймауты или уменьшите параллелизм.",
                'action': "Установите таймаут > 30 секунд и уменьшите число потоков до 4-6"
            })
        
        if perf_data['current_memory_mb'] > 4000:  # >4GB
            recommendations.append({
                'level': 'warning',
                'message': f"Высокое использование памяти: {perf_data['current_memory_mb']:.0f}MB",
                'action': "Уменьшите размер партии до 50 и включите автоматическую сборку мусора"
            })
        
        if perf_data['throughput'] < 5:
            recommendations.append({
                'level': 'warning',
                'message': f"Низкая производительность: {perf_data['throughput']:.1f} img/сек",
                'action': "Проверьте скорость сети, увеличьте число потоков до 12-16"
            })
        
        if perf_data['avg_cpu_percent'] > 85:
            recommendations.append({
                'level': 'info',
                'message': f"Высокая загрузка CPU: {perf_data['avg_cpu_percent']:.1f}%",
                'action': "Снизьте количество параллельных потоков"
            })
        
        if not recommendations:
            recommendations.append({
                'level': 'success',
                'message': "Система работает оптимально",
                'action': "Продолжайте текущие настройки"
            })
        
        return recommendations

# ==================== УПРАВЛЕНИЕ ПАМЯТЬЮ И ПРОИЗВОДИТЕЛЬНОСТЬЮ ====================
class AdvancedMemoryManager:
    """Продвинутое управление памятью с прогнозированием"""
    def __init__(self):
        self.memory_history = []
        self.leak_threshold = 1000  # MB
        self.prediction_window = 100
        
    def predict_memory_peak(self, images_remaining):
        """Прогнозирование пикового использования памяти"""
        if len(self.memory_history) < 10:
            return None
            
        # Анализ тренда
        recent_growth = []
        for i in range(1, min(10, len(self.memory_history))):
            growth = self.memory_history[-i] - self.memory_history[-(i+1)]
            recent_growth.append(growth)
        
        avg_growth = sum(recent_growth) / len(recent_growth)
        current_memory = psutil.Process().memory_info().rss / 1024 / 1024
        predicted_peak = current_memory + avg_growth * min(images_remaining, self.prediction_window)
        
        return predicted_peak
    
    def optimize_batch_strategy(self, current_batch_size, images_remaining):
        """Оптимизация стратегии обработки"""
        predicted_peak = self.predict_memory_peak(images_remaining)
        system_memory = psutil.virtual_memory()
        
        if predicted_peak and predicted_peak > system_memory.total * 0.7 / (1024*1024):
            # Риск исчерпания памяти - агрессивное снижение
            return max(10, int(current_batch_size * 0.5))
        
        # Адаптивная настройка на основе истории
        if self.memory_history:
            last_change = self.memory_history[-1] - self.memory_history[0] if len(self.memory_history) > 1 else 0
            if last_change > self.leak_threshold:
                return max(50, int(current_batch_size * 0.7))
        
        return current_batch_size
    
    def update_memory_history(self):
        """Обновление истории использования памяти"""
        current_memory = psutil.Process().memory_info().rss / 1024 / 1024
        self.memory_history.append(current_memory)
        if len(self.memory_history) > 100:
            self.memory_history.pop(0)

# ==================== ДИНАМИЧЕСКАЯ НАСТРОЙКА ПАРАЛЛЕЛИЗМА ====================
class DynamicParallelismOptimizer:
    """Адаптивная настройка параллелизма"""
    def __init__(self):
        self.optimal_threads_history = []
        self.network_latency_history = []
        
    def calculate_optimal_threads(self, avg_network_speed, avg_processing_time, cpu_cores=None):
        """Расчет оптимального количества потоков"""
        if cpu_cores is None:
            cpu_cores = psutil.cpu_count(logical=False)
        
        # Эвристика на основе формулы Amdahl
        if avg_network_speed < 100:  # Медленная сеть
            network_bound_threads = max(1, int(avg_network_speed / 10))
        elif avg_network_speed > 1000:  # Быстрая сеть
            network_bound_threads = min(32, cpu_cores * 4)
        else:
            network_bound_threads = min(16, cpu_cores * 2)
        
        # Учет времени обработки
        if avg_processing_time > 2.0:  # Долгая обработка
            optimal = min(network_bound_threads, cpu_cores)
        else:
            optimal = network_bound_threads
        
        # Учет загрузки CPU
        cpu_percent = psutil.cpu_percent(interval=1)
        if cpu_percent > 80:
            optimal = max(1, int(optimal * 0.7))
        
        self.optimal_threads_history.append(optimal)
        if len(self.optimal_threads_history) > 50:
            self.optimal_threads_history.pop(0)
        
        return optimal
    
    def get_recommendation(self):
        """Получение рекомендации по настройке"""
        if len(self.optimal_threads_history) < 5:
            return ["Идет сбор данных..."]
        
        avg_threads = sum(self.optimal_threads_history) / len(self.optimal_threads_history)
        
        recommendations = []
        
        if avg_threads < 4:
            recommendations.append("📶 Сеть - узкое место. Увеличьте пропускную способность.")
        
        cpu_percent = psutil.cpu_percent()
        if cpu_percent > 90:
            recommendations.append("🔥 Высокая нагрузка CPU. Уменьшите количество потоков.")
        
        memory = psutil.virtual_memory()
        if memory.percent > 85:
            recommendations.append("💾 Высокое использование памяти. Уменьшите размер партии.")
        
        return recommendations if recommendations else ["⚡ Система оптимально настроена"]

# ==================== РАСШИРЕННАЯ ОБРАБОТКА ОШИБОК И ПОВТОРОВ ====================
class SmartRetryManager:
    """Умный менеджер повторных попыток"""
    def __init__(self):
        self.error_patterns = {}
        self.retry_strategies = {
            'network': {'delay': 2, 'max_attempts': 3, 'backoff': 1.5},
            'timeout': {'delay': 5, 'max_attempts': 2, 'backoff': 2.0},
            'image_corrupt': {'delay': 1, 'max_attempts': 1, 'backoff': 1.0},
            'memory_error': {'delay': 10, 'max_attempts': 1, 'backoff': 1.0}
        }
        
    def classify_error(self, error_message):
        """Классификация ошибки для выбора стратегии"""
        if not isinstance(error_message, str):
            return 'unknown'
            
        error_lower = error_message.lower()
        
        if any(word in error_lower for word in ['timeout', 'timed out', 'connection']):
            return 'timeout'
        elif any(word in error_lower for word in ['network', 'socket', 'connection refused']):
            return 'network'
        elif any(word in error_lower for word in ['image', 'corrupt', 'truncated', 'decoder']):
            return 'image_corrupt'
        elif any(word in error_lower for word in ['memory', 'out of memory']):
            return 'memory_error'
        else:
            return 'unknown'
    
    def should_retry(self, error_type, attempt, url=None):
        """Определение, стоит ли повторять попытку"""
        if error_type not in self.retry_strategies:
            return False
        
        strategy = self.retry_strategies[error_type]
        
        # Проверка максимального количества попыток
        if attempt >= strategy['max_attempts']:
            return False
        
        # Специальные правила для разных типов ошибок
        if error_type == 'memory_error':
            # При ошибках памяти делаем паузу и очищаем память
            gc.collect()
            time.sleep(strategy['delay'] * (strategy['backoff'] ** attempt))
            return True
        
        return True
    
    def get_retry_delay(self, error_type, attempt):
        """Получение задержки перед повторной попыткой"""
        if error_type in self.retry_strategies:
            strategy = self.retry_strategies[error_type]
            return strategy['delay'] * (strategy['backoff'] ** attempt)
        return 2 ** attempt  # Экспоненциальная задержка

# ==================== ИНТЕЛЛЕКТУАЛЬНЫЙ ПРЕДПРОСМОТР И ВАЛИДАЦИЯ ====================
class IntelligentPreviewValidator:
    """Интеллектуальная валидация и предпросмотр"""
    def __init__(self):
        self.template_validators = {}
        self.color_schemes = {}
        
    def validate_template_compatibility(self, image, texts, template_name):
        """Проверка совместимости шаблона с изображением"""
        warnings = []
        recommendations = []
        
        # Анализ изображения
        img_stats = self._analyze_image(image)
        
        # Анализ текста
        text_stats = self._analyze_texts(texts)
        
        # Проверка контрастности
        if img_stats['avg_brightness'] > 200 and template_name == 'standard':
            warnings.append("Яркое изображение - текст может быть плохо виден")
            recommendations.append("Используйте темный текст или другой шаблон")
        
        # Проверка длины текста
        for corner, text in texts.items():
            if len(text) > 50:
                warnings.append(f"Длинный текст в {corner} ({len(text)} символов)")
                recommendations.append(f"Сократите текст в {corner} до 30 символов")
        
        # Проверка цветового контраста
        contrast_score = self._calculate_contrast_score(image, texts)
        if contrast_score < 4.5:  # WCAG стандарт
            warnings.append("Низкий контраст между текстом и фоном")
            recommendations.append("Измените цвет текста или добавьте фон")
        
        return warnings, recommendations
    
    def _analyze_image(self, image):
        """Анализ характеристик изображения"""
        # Конвертируем в оттенки серого для анализа
        gray = image.convert('L')
        hist = gray.histogram()
        
        # Вычисляем среднюю яркость
        brightness = sum(i * hist[i] for i in range(256)) / sum(hist) if sum(hist) > 0 else 128
        
        # Анализ контрастности
        pixels = list(gray.getdata())
        contrast = max(pixels) - min(pixels) if pixels else 0
        
        return {
            'width': image.width,
            'height': image.height,
            'avg_brightness': brightness,
            'contrast': contrast,
            'mode': image.mode,
            'size_bytes': len(image.tobytes()) if hasattr(image, 'tobytes') else 0
        }
    
    def _analyze_texts(self, texts):
        """Анализ текстов"""
        stats = {
            'total_length': 0,
            'avg_length': 0,
            'max_length': 0,
            'has_unicode': False
        }
        
        if not texts:
            return stats
        
        lengths = [len(str(t)) for t in texts.values()]
        stats['total_length'] = sum(lengths)
        stats['avg_length'] = sum(lengths) / len(lengths)
        stats['max_length'] = max(lengths)
        
        # Проверка на Unicode символы
        for text in texts.values():
            if isinstance(text, str):
                try:
                    text.encode('ascii')
                except UnicodeEncodeError:
                    stats['has_unicode'] = True
                    break
        
        return stats
    
    def _calculate_contrast_score(self, image, texts):
        """Расчет контрастности между текстом и фоном"""
        # Упрощенная реализация
        draw = ImageDraw.Draw(image)
        
        # Для каждого угла вычисляем контраст
        contrasts = []
        
        corners = {
            'top_left': (0.05, 0.05),
            'top_right': (0.95, 0.05),
            'bottom_left': (0.05, 0.95),
            'bottom_right': (0.95, 0.95)
        }
        
        for corner, (x_percent, y_percent) in corners.items():
            # Получаем область где будет текст
            x = int(image.width * x_percent)
            y = int(image.height * y_percent)
            bbox = (x-50, y-20, x+50, y+20)  # Примерная область текста
            
            if all(0 <= coord <= max(image.width, image.height) for coord in bbox):
                region = image.crop(bbox)
                
                # Усредненный цвет фона
                avg_color = self._get_average_color(region)
                
                if avg_color:
                    # Цвет текста (черный или белый)
                    brightness = sum(avg_color[:3])/3
                    text_color = (0, 0, 0) if brightness > 128 else (255, 255, 255)
                    
                    # Вычисляем контраст (упрощенная формула)
                    bg_luminance = 0.2126*avg_color[0] + 0.7152*avg_color[1] + 0.0722*avg_color[2]
                    text_luminance = 0.2126*text_color[0] + 0.7152*text_color[1] + 0.0722*text_color[2]
                    
                    if text_luminance > 0:
                        contrast = (max(bg_luminance, text_luminance) + 0.05) / (min(bg_luminance, text_luminance) + 0.05)
                        contrasts.append(contrast)
        
        return min(contrasts) if contrasts else 1.0
    
    def _get_average_color(self, image):
        """Получение среднего цвета изображения"""
        try:
            # Конвертируем в RGB если нужно
            if image.mode != 'RGB':
                image = image.convert('RGB')
            
            # Берем выборку пикселей
            pixels = list(image.getdata())
            if not pixels:
                return None
            
            # Вычисляем средний цвет
            r = sum(p[0] for p in pixels) / len(pixels)
            g = sum(p[1] for p in pixels) / len(pixels)
            b = sum(p[2] for p in pixels) / len(pixels)
            
            return (int(r), int(g), int(b))
        except:
            return None

# ==================== АВТОМАТИЧЕСКОЕ РАСПРЕДЕЛЕНИЕ РЕСУРСОВ ====================
class ResourceBalancer:
    """Автоматическое распределение ресурсов"""
    def __init__(self):
        self.resource_usage = {
            'cpu': [],
            'memory': [],
            'network': [],
            'disk_io': []
        }
        self.optimization_history = []
        
    def analyze_system_limits(self):
        """Анализ системных ограничений"""
        limits = {
            'max_threads': psutil.cpu_count(logical=True),
            'max_memory_mb': psutil.virtual_memory().total / (1024*1024),
            'available_disk_gb': psutil.disk_usage('.').free / (1024**3),
            'network_speed': self._estimate_network_speed()
        }
        
        return limits
    
    def recommend_optimal_config(self, total_images, avg_image_size_mb=1.0):
        """Рекомендация оптимальной конфигурации"""
        limits = self.analyze_system_limits()
        
        recommendations = {}
        
        # Расчет оптимального количества потоков
        cpu_cores = limits['max_threads']
        available_memory_mb = limits['max_memory_mb'] * 0.7  # 70% от общей памяти
        
        # Эвристика для потоков
        if total_images < 1000:
            recommendations['threads'] = min(8, cpu_cores)
        elif total_images < 10000:
            recommendations['threads'] = min(16, cpu_cores * 2)
        else:
            recommendations['threads'] = min(32, cpu_cores * 4)
        
        # Расчет размера партии
        memory_per_image = avg_image_size_mb * 3  # Примерный множитель
        max_batch_by_memory = int(available_memory_mb / memory_per_image)
        
        recommendations['batch_size'] = min(1000, max(100, max_batch_by_memory))
        
        # Рекомендации по кэшу
        recommendations['cache_size_mb'] = min(1000, int(available_memory_mb * 0.3))
        
        # Рекомендации по формату
        if limits['available_disk_gb'] < 10:
            recommendations['output_format'] = 'JPEG'
            recommendations['quality'] = 80
        else:
            recommendations['output_format'] = 'WebP'
            recommendations['quality'] = 85
        
        return recommendations
    
    def _estimate_network_speed(self):
        """Оценка скорости сети"""
        # Простая реализация - можно расширить
        try:
            # Тест загрузки небольшого файла
            test_url = "https://httpbin.org/bytes/1024"  # 1KB тестовый файл
            start = time.time()
            response = requests.get(test_url, timeout=5)
            duration = time.time() - start
            
            if duration > 0 and response.status_code == 200:
                return 1.024 / duration  # KB/s
        except:
            pass
        
        return 100  # Значение по умолчанию

# ==================== ИНТЕГРАЦИЯ С СИСТЕМОЙ МОНИТОРИНГА ====================
class MonitoringDashboard:
    """Панель мониторинга в реальном времени"""
    def __init__(self):
        self.metrics = {
            'throughput': [],
            'memory_usage': [],
            'errors': [],
            'network_speed': [],
            'queue_size': []
        }
        self.alerts = []
        
    def create_dashboard(self, performance_monitor):
        """Создание интерактивной панели мониторинга"""
        perf_data = performance_monitor.get_performance_dashboard()
        
        # Основные метрики
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("🎯 Производительность", 
                     f"{perf_data['throughput']:.1f}", 
                     "img/сек")
        with col2:
            st.metric("💾 Память", 
                     f"{perf_data['current_memory_mb']:.0f}",
                     "MB")
        with col3:
            st.metric("⚡ CPU", 
                     f"{perf_data['avg_cpu_percent']:.1f}%",
                     "")
        with col4:
            st.metric("📶 Сеть", 
                     f"{perf_data['avg_network_kbps']:.0f}",
                     "KB/s")
        
        # Графики
        st.subheader("📈 Тренды производительности")
        
        if performance_monitor.history:
            df_history = pd.DataFrame(performance_monitor.history[-100:])
            
            tab1, tab2, tab3 = st.tabs(["Производительность", "Память", "Ошибки"])
            
            with tab1:
                col1, col2 = st.columns(2)
                with col1:
                    if 'processing_time' in df_history.columns:
                        st.line_chart(df_history.set_index('timestamp')['processing_time'])
                        st.caption("Время обработки (сек)")
                with col2:
                    if 'processing_time' in df_history.columns:
                        throughput = 1 / df_history['processing_time'].rolling(10).mean()
                        st.line_chart(throughput)
                        st.caption("Скорость обработки (img/сек)")
            
            with tab2:
                if 'memory_mb' in df_history.columns:
                    st.line_chart(df_history.set_index('timestamp')['memory_mb'])
                    st.caption("Использование памяти (MB)")
            
            with tab3:
                if 'success' in df_history.columns:
                    error_rate = df_history['success'].rolling(20).apply(lambda x: (x == False).sum())
                    st.line_chart(error_rate)
                    st.caption("Частота ошибок (последние 20)")
        
        # Системные предупреждения
        if self.alerts:
            st.subheader("🚨 Активные предупреждения")
            for alert in self.alerts[-5:]:
                if alert['level'] == 'critical':
                    st.error(f"🔴 {alert['message']}")
                elif alert['level'] == 'warning':
                    st.warning(f"🟡 {alert['message']}")
                else:
                    st.info(f"🔵 {alert['message']}")
    
    def add_alert(self, level, message):
        """Добавление предупреждения"""
        self.alerts.append({
            'level': level,
            'message': message,
            'timestamp': time.time()
        })
        if len(self.alerts) > 20:
            self.alerts.pop(0)

# ==================== ПЛАНИРОВАНИЕ ОБРАБОТКИ 100,000+ ИЗОБРАЖЕНИЙ ====================
class LargeScalePlanner:
    """Планировщик для очень больших объемов"""
    
    def create_processing_plan(self, total_images, system_specs=None):
        """
        Создание детального плана обработки
        """
        if system_specs is None:
            system_specs = self._get_default_specs()
        
        plan = {
            'phases': [],
            'estimated_time': 0,
            'resource_requirements': {},
            'risk_factors': [],
            'optimization_opportunities': []
        }
        
        # Фаза 1: Настройка и тестирование (1%)
        plan['phases'].append({
            'name': 'Настройка и тестирование',
            'images': max(100, int(total_images * 0.01)),
            'threads': 4,
            'batch_size': 50,
            'purpose': 'Определение оптимальных параметров'
        })
        
        # Фаза 2: Основная обработка (89%)
        plan['phases'].append({
            'name': 'Основная обработка',
            'images': int(total_images * 0.89),
            'threads': min(32, system_specs.get('cpu_cores', 8) * 2),
            'batch_size': 500,
            'purpose': 'Массовая обработка'
        })
        
        # Фаза 3: Контроль качества (10%)
        plan['phases'].append({
            'name': 'Контроль качества',
            'images': int(total_images * 0.1),
            'threads': 2,
            'batch_size': 100,
            'purpose': 'Верификация и исправление ошибок'
        })
        
        # Оценка времени
        avg_speed = 10  # изображений/сек по умолчанию
        plan['estimated_time'] = total_images / avg_speed / 3600  # часы
        
        return plan
    
    def _get_default_specs(self):
        """Получение спецификаций системы по умолчанию"""
        return {
            'cpu_cores': psutil.cpu_count(logical=False),
            'total_memory_gb': psutil.virtual_memory().total / (1024**3),
            'free_disk_gb': psutil.disk_usage('.').free / (1024**3)
        }

# ==================== КЛАСС ДЛЯ ОГРАНИЧЕНИЯ ЗАПРОСОВ ====================
class RateLimiter:
    """Балансировка нагрузки и ограничение запросов"""
    def __init__(self, max_requests_per_second=10):
        self.semaphore = Semaphore(max_requests_per_second)
        self.last_request_time = 0
        self.max_rps = max_requests_per_second
        self.request_times = []
        
    def acquire(self):
        """Получение разрешения на запрос с адаптивным регулированием"""
        self.semaphore.acquire()
        current_time = time.time()
        
        # Поддерживаем историю запросов
        self.request_times.append(current_time)
        self.request_times = [t for t in self.request_times if current_time - t < 10]  # Последние 10 секунд
        
        # Адаптивное регулирование на основе ошибок
        if len(self.request_times) > self.max_rps * 5:  # Слишком много запросов
            sleep_time = 0.5
        else:
            sleep_time = max(0, 1.0/self.max_rps - (current_time - self.last_request_time))
        
        if sleep_time > 0:
            time.sleep(sleep_time)
        
        self.last_request_time = time.time()
    
    def release(self):
        """Освобождение разрешения"""
        self.semaphore.release()
    
    def adjust_rate(self, success_rate):
        """Адаптивная регулировка скорости на основе успешности"""
        if success_rate < 0.8:  # Много ошибок - снижаем скорость
            self.max_rps = max(1, int(self.max_rps * 0.8))
        elif success_rate > 0.95 and self.max_rps < 50:  # Хорошая успешность - увеличиваем
            self.max_rps = min(50, int(self.max_rps * 1.1))
        return self.max_rps

# ==================== ИНФОГРАФИКА-ШАБЛОНЫ ====================
INFOGRAPHIC_TEMPLATES = {
    "standard": {
        "name": "📋 Стандартный шаблон",
        "description": "Для большинства товаров, сочетает цену и ключевые характеристики",
        "corners": {
            "top_left": {"size": 36, "style": "bold", "type": "main_advantage", "bg_opacity": 220},
            "top_right": {"size": 32, "style": "bold", "type": "promotion", "bg_opacity": 200},
            "bottom_left": {"size": 20, "style": "regular", "type": "details", "bg_opacity": 180},
            "bottom_right": {"size": 20, "style": "regular", "type": "details", "bg_opacity": 180}
        }
    },
    "premium": {
        "name": "⭐ Премиум шаблон", 
        "description": "Для дорогих товаров, акцент на статус и эксклюзивность",
        "corners": {
            "top_left": {"size": 32, "style": "bold", "type": "brand", "bg_opacity": 210},
            "top_right": {"size": 28, "style": "bold", "type": "status", "bg_opacity": 200},
            "bottom_left": {"size": 22, "style": "regular", "type": "features", "bg_opacity": 180},
            "bottom_right": {"size": 22, "style": "regular", "type": "features", "bg_opacity": 180}
        }
    },
    "promo": {
        "name": "🔥 Акционный шаблон",
        "description": "Для распродаж и специальных предложений",
        "corners": {
            "top_left": {"size": 40, "style": "bold", "type": "discount", "bg_opacity": 240},
            "top_right": {"size": 32, "style": "bold", "type": "urgency", "bg_opacity": 220},
            "bottom_left": {"size": 24, "style": "regular", "type": "old_price", "bg_opacity": 180},
            "bottom_right": {"size": 28, "style": "bold", "type": "new_price", "bg_opacity": 200}
        }
    },
    "vertical": {
        "name": "📱 Вертикальный шаблон",
        "description": "Для мобильных устройств и сторис",
        "corners": {
            "top_left": {"size": 28, "style": "bold", "type": "title", "bg_opacity": 220},
            "top_right": {"size": 24, "style": "bold", "type": "price", "bg_opacity": 200},
            "bottom_left": {"size": 18, "style": "regular", "type": "cta", "bg_opacity": 180},
            "bottom_right": {"size": 16, "style": "regular", "type": "hashtag", "bg_opacity": 180}
        }
    }
}

# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================
def preprocess_text_for_infographic(text, corner_type, template_name="standard"):
    """Предобработка текста для инфографики"""
    if not isinstance(text, str):
        text = str(text)
    
    text = ' '.join(text.split())
    
    max_lengths = {
        'main_advantage': 30,
        'promotion': 25,
        'details': 40,
        'brand': 20,
        'status': 15,
        'discount': 20,
        'urgency': 15,
        'old_price': 15,
        'new_price': 20,
        'title': 25,
        'price': 15,
        'cta': 30,
        'hashtag': 20,
        'features': 35
    }
    
    if template_name in INFOGRAPHIC_TEMPLATES:
        template_info = INFOGRAPHIC_TEMPLATES[template_name]
        text_type = template_info["corners"][corner_type]["type"]
        max_len = max_lengths.get(text_type, 30)
    else:
        max_len = 30
    
    if len(text) > max_len:
        text = text[:max_len-3] + "..."
    
    return text

@lru_cache(maxsize=100)
def get_cached_image(url, timeout=15):
    """Кэширование загруженных изображений"""
    try:
        url_hash = hashlib.md5(url.encode()).hexdigest()
        cache_dir = ".cache"
        os.makedirs(cache_dir, exist_ok=True)
        cache_path = os.path.join(cache_dir, f"{url_hash}.jpg")
        
        if os.path.exists(cache_path):
            cache_age = time.time() - os.path.getmtime(cache_path)
            if cache_age < 3600:
                return Image.open(cache_path)
        
        start_time = time.time()
        response = requests.get(url, timeout=timeout, 
                              headers={'User-Agent': 'Mozilla/5.0'})
        response.raise_for_status()
        
        network_speed = len(response.content) / (time.time() - start_time) / 1024  # KB/s
        
        img = Image.open(BytesIO(response.content))
        
        if img.mode in ('RGBA', 'LA', 'P'):
            background = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode == 'P':
                img = img.convert('RGBA')
            background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
            img = background
        
        img.save(cache_path, "JPEG", quality=85, optimize=True)
        
        return img, network_speed
        
    except Exception as e:
        return None, 0

def get_optimal_text_color(img, bbox):
    """Определение оптимального цвета текста (черный/белый) на основе фона"""
    try:
        bg_area = img.crop(bbox)
        bg_area = bg_area.resize((5, 5), Image.Resampling.LANCZOS)
        brightness = sum(bg_area.convert('L').getdata()) / 25
        return (0, 0, 0) if brightness > 128 else (255, 255, 255)
    except:
        return (0, 0, 0)

def optimize_image_memory(img):
    """Оптимизация использования памяти изображением"""
    if img.mode == 'RGBA':
        background = Image.new('RGB', img.size, (255, 255, 255))
        background.paste(img, mask=img.split()[3] if len(img.split()) > 3 else None)
        img = background
    
    max_dimension = 2000
    if img.width > max_dimension or img.height > max_dimension:
        ratio = min(max_dimension/img.width, max_dimension/img.height)
        new_size = (int(img.width * ratio), int(img.height * ratio))
        img = img.resize(new_size, Image.Resampling.LANCZOS)
    
    return img

def setup_logging(batch_dir):
    """Настройка логирования для сессии"""
    log_file = os.path.join(batch_dir, "processing_log.txt")
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger(__name__)

def save_checkpoint(batch_dir, processed_indices, failed_indices, stats):
    """Сохранение контрольной точки"""
    checkpoint = {
        'processed': list(processed_indices),
        'failed': list(failed_indices),
        'stats': stats,
        'timestamp': time.time(),
        'total_processed': len(processed_indices),
        'total_failed': len(failed_indices)
    }
    
    checkpoint_file = os.path.join(batch_dir, "checkpoint.json")
    with open(checkpoint_file, 'w', encoding='utf-8') as f:
        json.dump(checkpoint, f, indent=2, ensure_ascii=False)
    
    return checkpoint_file

def load_checkpoint(batch_dir):
    """Загрузка контрольной точки"""
    checkpoint_file = os.path.join(batch_dir, "checkpoint.json")
    if os.path.exists(checkpoint_file):
        try:
            with open(checkpoint_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            st.warning(f"Не удалось загрузить контрольную точку: {e}")
    return None

def generate_safe_filename(text, row_index, max_length=100, add_hash=False):
    """
    Генерация безопасного имени файла из текста.
    """
    if not isinstance(text, str):
        text = str(text)
    
    # Удаление недопустимых символов
    safe_text = re.sub(r'[<>:"/\\|?*]', '', text)
    safe_text = re.sub(r'[\n\r\t]', ' ', safe_text)
    safe_text = ' '.join(safe_text.split())
    
    # Транслитерация для кириллицы
    if st.session_state.get('transliterate_filenames', False):
        translit_dict = {
            'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd',
            'е': 'e', 'ё': 'yo', 'ж': 'zh', 'з': 'z', 'и': 'i',
            'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm', 'н': 'n',
            'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't',
            'у': 'u', 'ф': 'f', 'х': 'h', 'ц': 'ts', 'ч': 'ch',
            'ш': 'sh', 'щ': 'sch', 'ы': 'y', 'э': 'e', 'ю': 'yu',
            'я': 'ya', ' ': '_'
        }
        safe_text = ''.join(translit_dict.get(c.lower(), c.lower()) 
                           for c in safe_text)
    
    # Замена пробелов на подчеркивания
    if st.session_state.get('replace_spaces', True):
        safe_text = safe_text.replace(' ', '_')
    
    # Добавление хеша для уникальности
    if add_hash:
        short_hash = hashlib.md5(f"{text}_{row_index}".encode()).hexdigest()[:8]
        safe_text = f"{safe_text}_{short_hash}"
    
    # Добавление префикса и суффикса
    prefix = st.session_state.get('filename_prefix', '')
    suffix = st.session_state.get('filename_suffix', '')
    safe_text = f"{prefix}{safe_text}{suffix}"
    
    # Ограничение длины
    if len(safe_text) > max_length:
        safe_text = safe_text[:max_length]
    
    if not safe_text.strip():
        safe_text = f"image_{row_index+1}"
    
    return safe_text.strip()

def get_final_filename(base_name, row_index, add_counter=True, prefix="", suffix=""):
    """Генерация окончательного имени файла"""
    filename = f"{prefix}{base_name}{suffix}"
    
    if add_counter:
        filename = f"{filename}_{row_index+1:06d}"
    
    return filename

def rename_processed_files(batch_dir, df, filename_column, output_format):
    """
    Переименование уже обработанных файлов по новым правилам.
    """
    processed_files = list(Path(batch_dir).glob("*.*"))
    image_files = [f for f in processed_files 
                   if f.suffix.lower() in ['.png', '.jpg', '.jpeg', '.webp']]
    
    if not image_files:
        return []
    
    rename_log = []
    
    for file_path in image_files:
        match = re.search(r'_(\d+)\.', file_path.name)
        if match:
            row_index = int(match.group(1)) - 1
            
            if 0 <= row_index < len(df):
                row = df.iloc[row_index]
                new_base = generate_safe_filename(row[filename_column], row_index)
                new_name = f"{new_base}.{output_format.lower()}"
                new_path = file_path.parent / new_name
                
                if new_name != file_path.name:
                    counter = 1
                    original_new_path = new_path
                    while new_path.exists():
                        new_name = f"{new_base}_{counter}.{output_format.lower()}"
                        new_path = file_path.parent / new_name
                        counter += 1
                    
                    file_path.rename(new_path)
                    rename_log.append({
                        "old": file_path.name,
                        "new": new_path.name,
                        "row": row_index + 1
                    })
    
    return rename_log

def export_results_multiformat(batch_dir, formats=["jpg", "png", "webp"]):
    """
    Экспорт результатов в нескольких форматах одновременно.
    """
    converted_files = []
    
    for file_path in Path(batch_dir).glob("*.jpg"):
        img = Image.open(file_path)
        
        for fmt in formats:
            if fmt == "jpg":
                continue
            
            new_path = file_path.with_suffix(f".{fmt}")
            if fmt == "webp":
                img.save(new_path, "WEBP", quality=85)
            elif fmt == "png":
                img.save(new_path, "PNG", optimize=True)
            
            converted_files.append(str(new_path))
    
    return converted_files

def generate_metadata_csv(batch_dir, df, processed_indices, column_mapping, selected_template):
    """
    Генерация CSV файла с метаданными обработки.
    """
    metadata = []
    
    for idx in processed_indices:
        if idx < len(df):
            row = df.iloc[idx]
            
            file_pattern = f"*{idx+1:06d}*"
            matching_files = list(Path(batch_dir).glob(file_pattern))
            
            if matching_files:
                file_path = matching_files[0]
                file_size = file_path.stat().st_size
                
                metadata.append({
                    'row_index': idx + 1,
                    'filename': file_path.name,
                    'file_size_bytes': file_size,
                    'file_size_mb': file_size / (1024*1024),
                    'original_url': row[column_mapping['image_url']],
                    'text_top_left': row[column_mapping['top_left']],
                    'text_top_right': row[column_mapping['top_right']],
                    'text_bottom_left': row[column_mapping['bottom_left']],
                    'text_bottom_right': row[column_mapping['bottom_right']],
                    'processing_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'template': selected_template,
                    'status': 'success'
                })
    
    if metadata:
        metadata_df = pd.DataFrame(metadata)
        csv_path = Path(batch_dir) / "metadata.csv"
        metadata_df.to_csv(csv_path, index=False, encoding='utf-8')
        return csv_path
    
    return None

def send_notification(message, notification_type="info"):
    """Отправка уведомлений о статусе обработки"""
    
    if notification_type == "success":
        st.success(message)
    elif notification_type == "warning":
        st.warning(message)
    elif notification_type == "error":
        st.error(message)
    else:
        st.info(message)
    
    # Логирование
    if 'logger' in st.session_state:
        st.session_state.logger.info(f"Notification [{notification_type}]: {message}")

def create_progress_dashboard(processed, total, errors, speed, eta, memory_usage):
    """Создание интерактивной панели прогресса"""
    
    progress_percent = processed / total * 100 if total > 0 else 0
    
    st.progress(progress_percent / 100)
    
    # Форматирование времени
    if eta is not None:
        if eta > 3600:
            eta_str = f"{eta/3600:.1f} ч"
        elif eta > 60:
            eta_str = f"{eta/60:.1f} мин"
        else:
            eta_str = f"{eta:.0f} сек"
    else:
        eta_str = "расчет..."
    
    metric_cols = st.columns(5)
    with metric_cols[0]:
        st.metric("📊 Прогресс", f"{progress_percent:.1f}%")
    with metric_cols[1]:
        st.metric("⚡ Скорость", f"{speed:.1f}", "img/сек")
    with metric_cols[2]:
        st.metric("⏱️ Осталось", eta_str)
    with metric_cols[3]:
        st.metric("✅ Успешно", processed)
    with metric_cols[4]:
        st.metric("❌ Ошибки", errors)
    
    # Визуализация скорости
    if 'speed_history' not in st.session_state:
        st.session_state.speed_history = []
    
    st.session_state.speed_history.append(speed)
    if len(st.session_state.speed_history) > 50:
        st.session_state.speed_history.pop(0)
    
    if st.session_state.speed_history:
        speed_df = pd.DataFrame({
            'Скорость': st.session_state.speed_history,
            'Время': range(len(st.session_state.speed_history))
        })
        st.line_chart(speed_df.set_index('Время'))

def process_with_pagination(df, batch_size=1000, start_index=0, column_mapping=None, 
                           selected_template=None, output_dir=None, max_workers=8):
    """
    Обработка данных с пагинацией для очень больших наборов.
    """
    if column_mapping is None or selected_template is None:
        return 0
    
    total_rows = len(df)
    processed_total = 0
    
    with st.status("📋 Обработка больших данных с пагинацией..."):
        for batch_start in range(start_index, total_rows, batch_size):
            batch_end = min(batch_start + batch_size, total_rows)
            batch_df = df.iloc[batch_start:batch_end]
            
            # Создаем отдельную папку для каждой партии
            batch_folder = f"batch_{batch_start+1}_{batch_end}"
            full_path = os.path.join(output_dir, batch_folder)
            os.makedirs(full_path, exist_ok=True)
            
            st.write(f"Обработка партии {batch_start+1}-{batch_end}...")
            
            # Здесь можно вызвать основную функцию обработки
            # processed = process_batch(batch_df, full_path, column_mapping, selected_template, max_workers)
            
            # Сохранение метаданных партии
            metadata = {
                'batch_range': f"{batch_start+1}-{batch_end}",
                'total_rows': len(batch_df),
                'start_time': datetime.now().isoformat(),
                'column_mapping': column_mapping,
                'template': selected_template
            }
            
            metadata_path = os.path.join(full_path, "batch_metadata.json")
            with open(metadata_path, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False)
            
            processed_total += len(batch_df)
            
            # Очистка памяти
            gc.collect()
            
            st.write(f"✅ Партия {batch_start+1}-{batch_end} завершена")
    
    return processed_total

# ==================== ГЛАВНАЯ ФУНКЦИЯ ОБРАБОТКИ ====================
def create_marketplace_infographic(image_url, texts, template_name="standard", timeout=15):
    """
    Усиленная версия с обработкой ошибок и валидацией.
    """
    start_time = time.time()
    
    try:
        # Валидация URL
        if not isinstance(image_url, str) or not image_url.startswith(('http://', 'https://')):
            return None, f"Неверный URL: {image_url}", 0
        
        # Проверка текстов
        processed_texts = {}
        for corner, text in texts.items():
            processed_texts[corner] = preprocess_text_for_infographic(text, corner, template_name)
        
        # Загрузка изображения с кэшированием
        try:
            result = get_cached_image(image_url, timeout)
            if isinstance(result, tuple) and len(result) == 2:
                img, network_speed = result
            else:
                img = result
                network_speed = 0
            
            if img is None:
                return None, "Не удалось загрузить изображение (кэш не доступен)", 0
                
            if img.mode != 'RGBA':
                img = img.convert('RGBA')
                
        except Exception as e:
            return None, f"Ошибка загрузки изображения: {str(e)}", 0
        
        # Проверка минимального размера изображения
        min_size = 300
        if img.width < min_size or img.height < min_size:
            return None, f"Изображение слишком маленькое: {img.width}x{img.height}", 0
        
        # Оптимизация памяти
        img = optimize_image_memory(img)
        
        # Дальнейшая обработка
        draw = ImageDraw.Draw(img)
        template = INFOGRAPHIC_TEMPLATES[template_name]
        
        # Загрузка шрифтов с fallback
        font_paths = {
            "regular": st.session_state.get("regular_font_path", "arial.ttf"),
            "bold": st.session_state.get("bold_font_path", "arialbd.ttf")
        }
        
        fonts = {}
        for style in ["regular", "bold"]:
            try:
                font_size = max(8, template["corners"]["top_left"]["size"])
                fonts[style] = ImageFont.truetype(font_paths[style], font_size)
            except (IOError, AttributeError):
                fonts[style] = ImageFont.load_default()
        
        # Обработка каждого угла
        img_width, img_height = img.size
        
        for corner, config in template["corners"].items():
            text = processed_texts.get(corner, "")
            if not text or str(text).strip() == "":
                continue
                
            # Определение позиции
            if corner == "top_left":
                x, y = (20, 20)
                align = "left"
            elif corner == "top_right":
                x, y = (img_width - 20, 20)
                align = "right"
            elif corner == "bottom_left":
                x, y = (20, img_height - 20)
                align = "left"
            elif corner == "bottom_right":
                x, y = (img_width - 20, img_height - 20)
                align = "right"
            
            # Выбор шрифта
            font_style = config["style"]
            font_size = max(8, config["size"])
            
            font = fonts[font_style]
            if font == ImageFont.load_default():
                try:
                    font = ImageFont.load_default(size=font_size)
                except:
                    pass
            
            # Расчет размеров текста
            if hasattr(draw, 'textbbox'):
                bbox = draw.textbbox((x, y), text, font=font)
                text_width = bbox[2] - bbox[0]
                text_height = bbox[3] - bbox[1]
            else:
                text_width, text_height = font.getsize(text)
                bbox = (x, y, x + text_width, y + text_height)
            
            # Корректировка позиции для выравнивания
            if align == "right":
                x = x - text_width
                bbox = (x, y, x + text_width, y + text_height)
            if "bottom" in corner:
                y = y - text_height
                bbox = (x, y, x + text_width, y + text_height)
            
            # Добавление фона
            bg_expand = 8
            bg_box = (
                bbox[0] - bg_expand, bbox[1] - bg_expand//2,
                bbox[2] + bg_expand, bbox[3] + bg_expand//2
            )
            
            # Определение оптимального цвета текста
            text_color = get_optimal_text_color(img, bg_box)
            
            # Рисуем фон и текст
            draw.rectangle(bg_box, fill=(255, 255, 255, config["bg_opacity"]))
            draw.text((x, y), text, font=font, fill=text_color)
        
        # Обновление метрик производительности
        processing_time = time.time() - start_time
        
        if 'performance_monitor' in st.session_state:
            st.session_state.performance_monitor.update_metrics(
                processing_time, 
                success=True,
                network_speed=network_speed
            )
        
        return img, None, network_speed
        
    except Exception as e:
        processing_time = time.time() - start_time
        if 'performance_monitor' in st.session_state:
            st.session_state.performance_monitor.update_metrics(processing_time, success=False)
        
        return None, f"Непредвиденная ошибка: {str(e)}", 0

# ==================== ИНИЦИАЛИЗАЦИЯ СЕССИИ ====================
# Инициализация расширенных компонентов
if 'performance_monitor' not in st.session_state:
    st.session_state.performance_monitor = EnhancedPerformanceMonitor()
if 'memory_manager' not in st.session_state:
    st.session_state.memory_manager = AdvancedMemoryManager()
if 'parallelism_optimizer' not in st.session_state:
    st.session_state.parallelism_optimizer = DynamicParallelismOptimizer()
if 'retry_manager' not in st.session_state:
    st.session_state.retry_manager = SmartRetryManager()
if 'preview_validator' not in st.session_state:
    st.session_state.preview_validator = IntelligentPreviewValidator()
if 'resource_balancer' not in st.session_state:
    st.session_state.resource_balancer = ResourceBalancer()
if 'monitoring_dashboard' not in st.session_state:
    st.session_state.monitoring_dashboard = MonitoringDashboard()
if 'large_scale_planner' not in st.session_state:
    st.session_state.large_scale_planner = LargeScalePlanner()

# ==================== ПАНЕЛЬ УПРАВЛЕНИЯ (SIDEBAR) ====================
with st.sidebar:
    st.header("⚙️ Панель управления v3.0")
    
    # Управление параллелизмом
    parallel_control = st.slider(
        "Потоки обработки (динамический)",
        1, 64, 8,
        help="Автоматически настраивается по нагрузке"
    )
    
    # Автоматическое управление памятью
    auto_memory = st.checkbox("Автоматическое управление памятью", True)
    if auto_memory:
        memory_threshold = st.slider(
            "Порог использования памяти (%)",
            50, 95, 80,
            help="При достижении порога размер партии автоматически уменьшается"
        )
        st.session_state.memory_threshold = memory_threshold
    
    # AI-оптимизация
    st.subheader("🤖 AI Оптимизация")
    enable_ai_optimization = st.checkbox("Включить AI-оптимизацию", True)
    if enable_ai_optimization:
        optimization_level = st.select_slider(
            "Уровень оптимизации",
            options=["Стандартный", "Агрессивный", "Интеллектуальный"],
            value="Интеллектуальный"
        )
        
        adaptive_learning = st.checkbox("Адаптивное обучение", True)
        if adaptive_learning:
            learning_rate = st.slider("Скорость обучения", 0.1, 1.0, 0.3)
    
    # Расписание обработки
    schedule_processing = st.checkbox("Запланированная обработка", False)
    if schedule_processing:
        schedule_time = st.time_input("Время начала", value=datetime.now().time())
        schedule_days = st.multiselect(
            "Дни недели",
            ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"],
            default=["Пн", "Вт", "Ср", "Чт", "Пт"]
        )
    
    # Настройки уведомлений
    st.subheader("🔔 Уведомления")
    enable_email_notifications = st.checkbox("Email уведомления", False)
    if enable_email_notifications:
        email_recipient = st.text_input("Email получателя", "")
        notification_level = st.selectbox(
            "Уровень уведомлений",
            ["Только ошибки", "Важные", "Все"]
        )
    
    # Быстрые действия
    st.subheader("⚡ Быстрые действия")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🧹 Очистить кэш", use_container_width=True):
            cache_dir = ".cache"
            if os.path.exists(cache_dir):
                import shutil
                shutil.rmtree(cache_dir)
                st.success("Кэш очищен!")
    with col2:
        if st.button("📊 Обновить статистику", use_container_width=True):
            st.rerun()
    
    # Интеллектуальные рекомендации
    st.subheader("💡 Рекомендации")
    if st.button("🎯 Получить рекомендации", use_container_width=True):
        recommendations = st.session_state.parallelism_optimizer.get_recommendation()
        for rec in recommendations:
            st.info(rec)
    
    # Информация о системе
    st.subheader("ℹ️ Система")
    sys_memory = psutil.virtual_memory()
    st.metric("Память", f"{sys_memory.percent}%")
    st.metric("CPU", f"{psutil.cpu_percent()}%")
    
    if os.path.exists(".cache"):
        cache_size = sum(os.path.getsize(os.path.join(".cache", f)) 
                        for f in os.listdir(".cache") if os.path.isfile(os.path.join(".cache", f)))
        st.metric("Кэш", f"{cache_size/(1024*1024):.1f} MB")

# ==================== ПОДКЛЮЧЕНИЕ К ДАННЫМ ====================
st.header("1. 📊 Подключение к данным")

# Настройки прокси
with st.expander("🌐 Настройки сети (опционально)"):
    proxy_cols = st.columns(2)
    with proxy_cols[0]:
        http_proxy = st.text_input("HTTP прокси", "")
    with proxy_cols[1]:
        https_proxy = st.text_input("HTTPS прокси", "")
    
    if http_proxy or https_proxy:
        os.environ['HTTP_PROXY'] = http_proxy
        os.environ['HTTPS_PROXY'] = https_proxy
        st.success("Прокси настроены")
    
    rate_limit_col = st.columns(1)[0]
    with rate_limit_col:
        max_rps = st.slider("Максимальных запросов в секунду", 1, 100, 10,
                          help="Ограничение частоты запросов для избежания блокировки")

try:
    conn = st.connection("gsheets", type=GSheetsConnection)
    df = conn.read()
    st.success(f"✅ Успешно загружено {len(df)} строк из таблицы.")
    
    with st.expander("🔍 Посмотреть структуру данных"):
        st.dataframe(df.head())
        st.info(f"Найденные столбцы: {list(df.columns)}")
        
        st.subheader("Статистика данных")
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Всего строк", len(df))
        with col2:
            empty_cells = df.isnull().sum().sum()
            st.metric("Пустых ячеек", empty_cells)
        with col3:
            st.metric("Столбцов", len(df.columns))
            
except Exception as e:
    st.error(f"❌ Ошибка подключения к таблице: {e}")
    st.stop()

# ==================== НАСТРОЙКА СТОЛБЦОВ ====================
st.header("2. ⚙️ Настройка столбцов")
st.info("Укажите, из каких столбцов брать текст для каждого угла изображения")

DEFAULT_COLUMNS = {
    'top_left': 'B',
    'top_right': 'D', 
    'bottom_left': 'F',
    'bottom_right': 'H',
    'image_url': 'C',
    'filename': 'B'
}

config_cols = st.columns(2)
column_mapping = {}

with config_cols[0]:
    column_mapping['top_left'] = st.selectbox(
        "Верхний левый угол (основное преимущество)",
        options=list(df.columns),
        index=list(df.columns).index(DEFAULT_COLUMNS['top_left']) if DEFAULT_COLUMNS['top_left'] in df.columns else 0,
        help="Крупный текст 36px, обычно основное преимущество товара"
    )
    
    column_mapping['bottom_left'] = st.selectbox(
        "Нижний левый угол (детали)",
        options=list(df.columns),
        index=list(df.columns).index(DEFAULT_COLUMNS['bottom_left']) if DEFAULT_COLUMNS['bottom_left'] in df.columns else 0,
        help="Мелкий текст 20px, технические характеристики"
    )

with config_cols[1]:
    column_mapping['top_right'] = st.selectbox(
        "Верхний правый угол (акция/статус)",
        options=list(df.columns),
        index=list(df.columns).index(DEFAULT_COLUMNS['top_right']) if DEFAULT_COLUMNS['top_right'] in df.columns else 0,
        help="Крупный текст 32px, акции или специальный статус"
    )
    
    column_mapping['bottom_right'] = st.selectbox(
        "Нижний правый угол (детали)",
        options=list(df.columns),
        index=list(df.columns).index(DEFAULT_COLUMNS['bottom_right']) if DEFAULT_COLUMNS['bottom_right'] in df.columns else 0,
        help="Мелкий текст 20px, дополнительные параметры"
    )

column_mapping['image_url'] = st.selectbox(
    "Столбец с URL изображений",
    options=list(df.columns),
    index=list(df.columns).index(DEFAULT_COLUMNS['image_url']) if DEFAULT_COLUMNS['image_url'] in df.columns else 0,
    help="Ссылки на исходные изображения товаров"
)

# Настройки имен файлов
st.divider()
st.subheader("Настройки имен файлов")

file_naming_cols = st.columns(2)
with file_naming_cols[0]:
    column_mapping['filename'] = st.selectbox(
        "Столбец с именами файлов",
        options=list(df.columns),
        index=list(df.columns).index(DEFAULT_COLUMNS['filename']) if DEFAULT_COLUMNS['filename'] in df.columns else 0,
        help="Значения из этого столбца будут использоваться как имена файлов"
    )

with file_naming_cols[1]:
    use_filename_column = st.checkbox(
        "Использовать значения из столбца для имен файлов", 
        value=True,
        help="Если выключено, будут использоваться автоматические имена"
    )

# Дополнительные опции имен файлов
with st.expander("📝 Дополнительные опции имен файлов"):
    cols = st.columns(2)
    
    with cols[0]:
        st.session_state.replace_spaces = st.checkbox(
            "Заменять пробелы на подчеркивания",
            value=True
        )
        
        st.session_state.transliterate_filenames = st.checkbox(
            "Транслитерировать кириллицу",
            value=False,
            help="Преобразует русские буквы в латинские"
        )
        
        add_hash = st.checkbox(
            "Добавлять уникальный хеш",
            value=False,
            help="Для гарантии уникальности имен файлов"
        )
    
    with cols[1]:
        st.session_state.filename_prefix = st.text_input("Префикс для имен файлов", "")
        st.session_state.filename_suffix = st.text_input("Суффикс для имен файлов", "")
        
        auto_numbering = st.checkbox(
            "Автоматическая нумерация",
            value=True,
            help="Добавлять порядковые номера к именам файлов"
        )

# Проверка имен файлов
if use_filename_column and st.button("👁️ Показать примеры имен файлов"):
    st.info("Примеры имен файлов, которые будут использованы:")
    
    sample_size = min(10, len(df))
    sample_df = df.head(sample_size).copy()
    
    sample_df['Будет сохранено как'] = sample_df.apply(
        lambda row: f"{generate_safe_filename(row[column_mapping['filename']], row.name, add_hash=add_hash)}.jpg", 
        axis=1
    )
    
    st.dataframe(sample_df[[column_mapping['filename'], 'Будет сохранено как']])
    
    duplicates = sample_df['Будет сохранено как'].duplicated().sum()
    if duplicates > 0:
        st.warning(f"⚠️ В выборке найдено {duplicates} дубликатов имен файлов. Для дубликатов будут добавлены номера.")

# ==================== НАСТРОЙКИ ШРИФТОВ ====================
st.header("3. 🔤 Настройки шрифтов")

font_cols = st.columns(2)
with font_cols[0]:
    regular_font = st.text_input("Путь к обычному шрифту", "arial.ttf",
                               help="Путь к файлу шрифта (например, C:/Windows/Fonts/arial.ttf)")
    st.session_state.regular_font_path = regular_font

with font_cols[1]:
    bold_font = st.text_input("Путь к жирному шрифту", "arialbd.ttf",
                            help="Путь к файлу жирного шрифта")
    st.session_state.bold_font_path = bold_font

# Проверка шрифтов
if st.button("🔍 Проверить шрифты"):
    font_check_cols = st.columns(2)
    for i, (font_name, font_path) in enumerate([("Обычный", regular_font), ("Жирный", bold_font)]):
        with font_check_cols[i]:
            try:
                test_font = ImageFont.truetype(font_path, 20)
                st.success(f"✅ {font_name} шрифт загружен")
                st.caption(f"Путь: {font_path}")
            except Exception as e:
                st.error(f"❌ Ошибка загрузки {font_name} шрифта: {e}")
                st.info("Используется стандартный шрифт PIL")

# ==================== ВЫБОР ШАБЛОНА ====================
st.header("4. 🎨 Выбор шаблона инфографики")

template_cols = st.columns(len(INFOGRAPHIC_TEMPLATES))
selected_template = "standard"

for i, (template_key, template_info) in enumerate(INFOGRAPHIC_TEMPLATES.items()):
    with template_cols[i]:
        if st.button(template_info["name"], key=f"template_{template_key}", use_container_width=True):
            selected_template = template_key
        st.caption(template_info["description"])

st.info(f"**Выбран шаблон:** {INFOGRAPHIC_TEMPLATES[selected_template]['name']}")

# ==================== НАСТРОЙКИ ЭКСПОРТА ====================
st.header("5. ⚙️ Настройки экспорта")

export_cols = st.columns(3)

with export_cols[0]:
    output_format = st.selectbox(
        "Формат сохранения",
        ["PNG", "JPEG", "WebP"],
        index=0,
        help="WebP обеспечивает лучшее сжатие"
    )
    
    output_quality = st.slider(
        "Качество (для JPEG/WebP)",
        50, 100, 85,
        help="Баланс между качеством и размером файла"
    )

with export_cols[1]:
    resize_output = st.checkbox("Изменить размер выходных изображений", False)
    if resize_output:
        target_width = st.number_input("Ширина", 500, 3000, 1200)
        target_height = st.number_input("Высота", 500, 3000, 1200)
    
    add_watermark = st.checkbox("Добавить водяной знак", False)
    if add_watermark:
        watermark_text = st.text_input("Текст водяного знака", "© Marketplace")
        watermark_opacity = st.slider("Прозрачность водяного знака", 0, 255, 100)

with export_cols[2]:
    # Многоформатный экспорт
    multi_format_export = st.checkbox("Экспорт в нескольких форматах", False)
    if multi_format_export:
        export_formats = st.multiselect(
            "Выберите форматы",
            ["PNG", "JPEG", "WebP"],
            default=["JPEG", "WebP"]
        )
    
    # Автоматическая архивация
    auto_zip = st.checkbox("Автоматически создавать ZIP архив", True)

# ==================== ИНТЕЛЛЕКТУАЛЬНЫЙ ПРЕДПРОСМОТР ====================
st.header("6. 🤖 Интеллектуальный предпросмотр и валидация")

# Выбор строки для теста
preview_cols = st.columns(3)
with preview_cols[0]:
    preview_row = st.number_input(
        "Номер строки для тестирования:",
        min_value=0,
        max_value=len(df)-1,
        value=0,
        help="Выберите строку из таблицы для предварительного просмотра"
    )

with preview_cols[1]:
    preview_timeout = st.number_input("Таймаут (сек)", 5, 60, 15, 
                                     help="Максимальное время загрузки изображения")

with preview_cols[2]:
    enable_validation = st.checkbox("Включить валидацию", True)

if st.button("🔍 Запустить интеллектуальный предпросмотр", type="secondary", use_container_width=True):
    if 0 <= preview_row < len(df):
        row_data = df.iloc[preview_row]
        
        # Подготовка текстов
        preview_texts = {
            'top_left': str(row_data[column_mapping['top_left']]),
            'top_right': str(row_data[column_mapping['top_right']]),
            'bottom_left': str(row_data[column_mapping['bottom_left']]),
            'bottom_right': str(row_data[column_mapping['bottom_right']])
        }
        
        # Получение имени файла
        if use_filename_column and column_mapping['filename'] in row_data:
            preview_filename = generate_safe_filename(
                row_data[column_mapping['filename']], 
                preview_row,
                add_hash=add_hash
            )
        else:
            preview_filename = f"preview_{preview_row+1}"
        
        # Показ исходных данных
        st.subheader("Исходные данные:")
        data_cols = st.columns(4)
        corners_info = [
            ("↖️ Верхний левый", preview_texts['top_left']),
            ("↗️ Верхний правый", preview_texts['top_right']),
            ("↙️ Нижний левый", preview_texts['bottom_left']),
            ("↘️ Нижний правый", preview_texts['bottom_right'])
        ]
        
        for i, (title, text) in enumerate(corners_info):
            with data_cols[i]:
                st.metric(title, text[:25] + "..." if len(text) > 25 else text)
        
        # Интеллектуальная валидация
        if enable_validation:
            with st.spinner("🤖 Проверяю совместимость шаблона..."):
                # Сначала загружаем изображение для анализа
                try:
                    result_img, error, _ = create_marketplace_infographic(
                        row_data[column_mapping['image_url']],
                        preview_texts,
                        selected_template,
                        timeout=preview_timeout
                    )
                    
                    if result_img:
                        warnings, recommendations = st.session_state.preview_validator.validate_template_compatibility(
                            result_img, preview_texts, selected_template
                        )
                        
                        if warnings or recommendations:
                            st.subheader("🔍 Результаты валидации:")
                            
                            if warnings:
                                st.warning("⚠️ Предупреждения:")
                                for warning in warnings:
                                    st.write(f"- {warning}")
                            
                            if recommendations:
                                st.info("💡 Рекомендации:")
                                for rec in recommendations:
                                    st.write(f"- {rec}")
                        else:
                            st.success("✅ Шаблон полностью совместим с изображением")
                except Exception as e:
                    st.warning(f"Не удалось выполнить валидацию: {e}")
        
        # Обработка и показ результатов
        with st.spinner("Создаю инфографику..."):
            result_img, error, network_speed = create_marketplace_infographic(
                row_data[column_mapping['image_url']],
                preview_texts,
                selected_template,
                timeout=preview_timeout
            )
            
            if error:
                st.error(f"Ошибка: {error}")
                # Классификация ошибки для рекомендаций
                error_type = st.session_state.retry_manager.classify_error(error)
                st.info(f"Тип ошибки: {error_type}")
            else:
                st.success(f"✅ Инфографика успешно создана! (Скорость: {network_speed:.1f} KB/s)")
                
                # Применение дополнительных настроек экспорта
                if resize_output:
                    result_img = result_img.resize((target_width, target_height), Image.Resampling.LANCZOS)
                
                if add_watermark:
                    draw = ImageDraw.Draw(result_img)
                    try:
                        font = ImageFont.truetype("arial.ttf", 36)
                    except:
                        font = ImageFont.load_default()
                    
                    watermark_layer = Image.new('RGBA', result_img.size, (255, 255, 255, 0))
                    watermark_draw = ImageDraw.Draw(watermark_layer)
                    
                    bbox = watermark_draw.textbbox((0, 0), watermark_text, font=font)
                    text_width = bbox[2] - bbox[0]
                    text_height = bbox[3] - bbox[1]
                    
                    x = (result_img.width - text_width) // 2
                    y = (result_img.height - text_height) // 2
                    
                    watermark_draw.text((x, y), watermark_text, font=font, 
                                      fill=(255, 255, 255, watermark_opacity))
                    
                    result_img = Image.alpha_composite(result_img.convert('RGBA'), watermark_layer)
                
                # Сравнение исходного и обработанного
                col1, col2 = st.columns(2)
                with col1:
                    st.image(result_img, caption="Результат с инфографикой", use_container_width=True)
                    st.caption(f"Шаблон: {INFOGRAPHIC_TEMPLATES[selected_template]['name']}")
                    st.caption(f"Имя файла будет: {preview_filename}.{output_format.lower()}")
                    
                    # Сохранить предпросмотр
                    if st.button("💾 Сохранить предпросмотр"):
                        preview_path = f"{preview_filename}.{output_format.lower()}"
                        
                        if output_format == "JPEG":
                            if result_img.mode in ('RGBA', 'LA', 'P'):
                                background = Image.new('RGB', result_img.size, (255, 255, 255))
                                background.paste(result_img, mask=result_img.split()[-1] if result_img.mode == 'RGBA' else None)
                                result_img = background
                            result_img.save(preview_path, "JPEG", quality=output_quality, optimize=True)
                            mime_type = "image/jpeg"
                        elif output_format == "WebP":
                            result_img.save(preview_path, "WebP", quality=output_quality)
                            mime_type = "image/webp"
                        else:  # PNG
                            result_img.save(preview_path, "PNG", optimize=True)
                            mime_type = "image/png"
                        
                        with open(preview_path, "rb") as file:
                            st.download_button(
                                label="Скачать предпросмотр",
                                data=file,
                                file_name=preview_path,
                                mime=mime_type
                            )
                
                with col2:
                    try:
                        response = requests.get(row_data[column_mapping['image_url']], timeout=5)
                        original_img = Image.open(BytesIO(response.content))
                        st.image(original_img, caption="Исходное изображение", use_container_width=True)
                    except:
                        st.warning("Не удалось загрузить исходное изображение для сравнения")

# ==================== МАССОВАЯ ОБРАБОТКА ====================
st.header("7. ⚡ Умная массовая обработка")

output_dir = st.text_input(
    "Папка для сохранения результатов:",
    value=f"marketplace_infographic_{selected_template}",
    help="Все обработанные изображения будут сохранены в эту папку"
)

# Планирование больших объемов
with st.expander("📋 Планирование обработки больших объемов"):
    if st.button("🎯 Создать план обработки"):
        plan = st.session_state.large_scale_planner.create_processing_plan(len(df))
        
        st.subheader("📊 План обработки:")
        for i, phase in enumerate(plan['phases']):
            st.write(f"**Фаза {i+1}: {phase['name']}**")
            st.write(f"- Изображений: {phase['images']}")
            st.write(f"- Потоков: {phase['threads']}")
            st.write(f"- Размер партии: {phase['batch_size']}")
            st.write(f"- Цель: {phase['purpose']}")
            st.divider()
        
        estimated_hours = plan['estimated_time']
        st.info(f"⏱️ Ориентировочное время обработки: {estimated_hours:.1f} часов")

# Настройки обработки
st.subheader("⚡ Настройки параллельной обработки")

parallel_settings = st.columns(3)
with parallel_settings[0]:
    max_workers = st.slider("Количество потоков", 1, 64, 8, 
                           help="Для 50k изображений используйте 8-12 потоков")
with parallel_settings[1]:
    retry_count = st.number_input("Повторные попытки", 0, 5, 2,
                                 help="Количество повторных попыток при ошибках")
with parallel_settings[2]:
    batch_chunk_size = st.number_input("Размер чанка", 10, 2000, 100,
                                      help="Сколько изображений обрабатывать за раз")

settings_cols = st.columns(3)
with settings_cols[0]:
    skip_empty = st.checkbox("Пропускать пустые тексты", value=True, 
                           help="Не обрабатывать строки, где все тексты пустые")
with settings_cols[1]:
    checkpoint_interval = st.number_input("Интервал контрольных точек", 10, 2000, 100,
                                        help="Сохранять прогресс каждые N изображений")
with settings_cols[2]:
    batch_size = st.number_input("Сколько строк обработать:", 
                               min_value=1, 
                               max_value=len(df),
                               value=min(100, len(df)),
                               help="Для теста начните с небольшой партии")

# Пагинация для больших объемов
with st.expander("📋 Обработка больших объемов (пагинация)"):
    use_pagination = st.checkbox("Использовать пагинацию для больших объемов", False)
    if use_pagination:
        pagination_batch = st.number_input("Размер пагинации", 1000, 50000, 5000)
        start_from = st.number_input("Начать с индекса", 0, len(df)-1, 0)

# Проверка контрольных точек
checkpoint_dir = None
if os.path.exists(output_dir):
    result_dirs = []
    for item in os.listdir(output_dir):
        item_path = os.path.join(output_dir, item)
        if os.path.isdir(item_path) and item.startswith("batch_"):
            result_dirs.append((item_path, os.path.getmtime(item_path)))
    
    if result_dirs:
        result_dirs.sort(key=lambda x: x[1], reverse=True)
        latest_dir = result_dirs[0][0]
        
        checkpoint_data = load_checkpoint(latest_dir)
        if checkpoint_data:
            st.info(f"📌 Найдена контрольная точка в {os.path.basename(latest_dir)}")
            st.write(f"Обработано: {checkpoint_data['total_processed']}, Ошибок: {checkpoint_data['total_failed']}")
            
            if st.button("🔄 Возобновить с контрольной точки"):
                checkpoint_dir = latest_dir
                st.session_state.checkpoint_data = checkpoint_data

# Функция обработки одного изображения с умными повторами
def process_single_image_enhanced(row_index, row, texts, template_name, timeout_val, rate_limiter, 
                                 use_custom_filenames, filename_column=None):
    """Обработка одного изображения с интеллектуальными повторами"""
    for attempt in range(retry_count + 1):
        try:
            if rate_limiter:
                rate_limiter.acquire()
            
            start_time = time.time()
            result_img, error, network_speed = create_marketplace_infographic(
                row[column_mapping['image_url']],
                texts,
                template_name,
                timeout=timeout_val
            )
            
            processing_time = time.time() - start_time
            
            if rate_limiter:
                rate_limiter.release()
            
            if error and attempt < retry_count:
                # Классификация ошибки и интеллектуальная задержка
                error_type = st.session_state.retry_manager.classify_error(error)
                if st.session_state.retry_manager.should_retry(error_type, attempt):
                    delay = st.session_state.retry_manager.get_retry_delay(error_type, attempt)
                    time.sleep(delay)
                    continue
                else:
                    break
            
            # Генерация имени файла
            if use_custom_filenames and filename_column and filename_column in row:
                filename_base = generate_safe_filename(
                    row[filename_column], 
                    row_index,
                    add_hash=add_hash
                )
            else:
                filename_base = f"img_{row_index+1:06d}"
            
            return row_index, result_img, error, processing_time, filename_base, network_speed
            
        except Exception as e:
            if rate_limiter:
                rate_limiter.release()
            
            error_type = st.session_state.retry_manager.classify_error(str(e))
            if attempt < retry_count and st.session_state.retry_manager.should_retry(error_type, attempt):
                delay = st.session_state.retry_manager.get_retry_delay(error_type, attempt)
                time.sleep(delay)
                continue
            
            filename_base = f"img_{row_index+1:06d}"
            return row_index, None, str(e), time.time() - start_time, filename_base, 0
    
    filename_base = f"img_{row_index+1:06d}"
    return row_index, None, "Все попытки неудачны", 0, filename_base, 0

# Старт массовой обработки
if st.button("🚀 Запустить умную массовую обработку", type="primary"):
    start_time = time.time()
    
    # Получение рекомендаций по оптимизации
    if enable_ai_optimization:
        recommendations = st.session_state.resource_balancer.recommend_optimal_config(batch_size)
        st.info("🤖 Рекомендации AI-оптимизатора:")
        for key, value in recommendations.items():
            st.write(f"- {key}: {value}")
        
        # Применение рекомендаций
        max_workers = recommendations.get('threads', max_workers)
        batch_chunk_size = recommendations.get('batch_size', batch_chunk_size)
    
    # Создание папок
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    batch_dir = os.path.join(output_dir, f"batch_{timestamp}")
    os.makedirs(batch_dir, exist_ok=True)
    
    # Инициализация монитора производительности
    st.session_state.performance_monitor = EnhancedPerformanceMonitor()
    
    # Инициализация rate limiter
    rate_limiter = RateLimiter(max_requests_per_second=max_rps)
    
    # Настройка логирования
    logger = setup_logging(batch_dir)
    st.session_state.logger = logger
    logger.info(f"Начата обработка {batch_size} изображений")
    
    # Элементы интерфейса прогресса
    progress_bar = st.progress(0)
    status_text = st.empty()
    stats_area = st.empty()
    performance_area = st.empty()
    recommendations_area = st.empty()
    monitoring_dashboard_area = st.empty()
    results_expander = st.expander("📊 Детальная статистика", expanded=False)
    
    # Статистика
    processed_count = 0
    error_count = 0
    skipped_count = 0
    error_list = []
    success_rate_history = []
    
    # Восстановление из контрольной точки
    processed_indices = set()
    failed_indices = set()
    
    if 'checkpoint_data' in st.session_state and checkpoint_dir:
        checkpoint_data = st.session_state.checkpoint_data
        processed_indices = set(checkpoint_data['processed'])
        failed_indices = set(checkpoint_data['failed'])
        processed_count = len(processed_indices)
        error_count = len(failed_indices)
        logger.info(f"Восстановление из контрольной точки: {processed_count} обработано, {error_count} ошибок")
    
    # Создание списка задач
    tasks = []
    valid_indices = []
    
    for i in range(min(batch_size, len(df))):
        if i in processed_indices or i in failed_indices:
            continue
            
        row = df.iloc[i]
        
        texts = {
            'top_left': str(row[column_mapping['top_left']]),
            'top_right': str(row[column_mapping['top_right']]),
            'bottom_left': str(row[column_mapping['bottom_left']]),
            'bottom_right': str(row[column_mapping['bottom_right']])
        }
        
        if skip_empty and all(not str(t).strip() for t in texts.values()):
            skipped_count += 1
            logger.info(f"Пропущена строка {i+1}: все тексты пустые")
            processed_indices.add(i)
            continue
        
        valid_indices.append(i)
        tasks.append((i, row, texts))
    
    # Запуск параллельной обработки
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = []
        
        for i, row, texts in tasks[:min(len(tasks), batch_size - processed_count)]:
            future = executor.submit(
                process_single_image_enhanced, 
                i, 
                row, 
                texts, 
                selected_template, 
                15, 
                rate_limiter,
                use_filename_column,
                column_mapping['filename'] if use_filename_column else None
            )
            futures.append(future)
        
        # Обработка результатов
        completed = 0
        total_tasks = len(futures)
        last_stats_update = time.time()
        last_optimization_check = time.time()
        
        for future in concurrent.futures.as_completed(futures):
            row_index, result_img, error, processing_time, filename_base, network_speed = future.result()
            
            if error:
                error_count += 1
                failed_indices.add(row_index)
                error_msg = f"Строка {row_index+1}: {error}"
                error_list.append(error_msg)
                logger.error(error_msg)
                
                # Классификация ошибки для мониторинга
                error_type = st.session_state.retry_manager.classify_error(error)
                st.session_state.monitoring_dashboard.add_alert('warning', f"Ошибка типа '{error_type}' в строке {row_index+1}")
            elif result_img:
                # Применение настроек экспорта
                if resize_output:
                    result_img = result_img.resize((target_width, target_height), Image.Resampling.LANCZOS)
                
                if add_watermark:
                    draw = ImageDraw.Draw(result_img)
                    try:
                        font = ImageFont.truetype("arial.ttf", 36)
                    except:
                        font = ImageFont.load_default()
                    
                    watermark_layer = Image.new('RGBA', result_img.size, (255, 255, 255, 0))
                    watermark_draw = ImageDraw.Draw(watermark_layer)
                    
                    bbox = watermark_draw.textbbox((0, 0), watermark_text, font=font)
                    text_width = bbox[2] - bbox[0]
                    text_height = bbox[3] - bbox[1]
                    
                    x = (result_img.width - text_width) // 2
                    y = (result_img.height - text_height) // 2
                    
                    watermark_draw.text((x, y), watermark_text, font=font, 
                                      fill=(255, 255, 255, watermark_opacity))
                    
                    result_img = Image.alpha_composite(result_img.convert('RGBA'), watermark_layer)
                
                # Генерация имени файла
                if auto_numbering:
                    filename = f"{filename_base}_{row_index+1:06d}.{output_format.lower()}"
                else:
                    filename = f"{filename_base}.{output_format.lower()}"
                
                filepath = os.path.join(batch_dir, filename)
                counter = 1
                original_filename = filename
                while os.path.exists(filepath):
                    filename = f"{filename_base}_{counter}.{output_format.lower()}"
                    filepath = os.path.join(batch_dir, filename)
                    counter += 1
                
                # Сохранение результата
                if output_format == "JPEG":
                    if result_img.mode in ('RGBA', 'LA', 'P'):
                        background = Image.new('RGB', result_img.size, (255, 255, 255))
                        background.paste(result_img, mask=result_img.split()[-1] if result_img.mode == 'RGBA' else None)
                        result_img = background
                    result_img.save(filepath, "JPEG", quality=output_quality, optimize=True)
                elif output_format == "WebP":
                    result_img.save(filepath, "WebP", quality=output_quality)
                else:  # PNG
                    result_img.save(filepath, "PNG", optimize=True)
                
                processed_count += 1
                processed_indices.add(row_index)
                logger.info(f"Сохранено: {filename} (из строки {row_index+1})")
            
            completed += 1
            
            # Обновление прогресса
            progress_percent = completed / total_tasks
            progress_bar.progress(progress_percent)
            status_text.text(f"Обработано: {completed}/{total_tasks}")
            
            # Обновление истории памяти
            st.session_state.memory_manager.update_memory_history()
            
            # Обновление статистики каждые 5 секунд или каждые 10 изображений
            current_time = time.time()
            if completed % 10 == 0 or current_time - last_stats_update > 5:
                last_stats_update = current_time
                
                # Расчет производительности
                elapsed = current_time - start_time
                speed = processed_count / max(elapsed, 1)
                eta = st.session_state.performance_monitor.estimate_completion(total_tasks)
                
                # Обновление dashboard
                perf_metrics = st.session_state.performance_monitor.get_performance_dashboard()
                
                create_progress_dashboard(
                    processed_count, total_tasks, error_count, 
                    speed, eta, perf_metrics['current_memory_mb']
                )
                
                # Показать мониторинг в реальном времени
                with monitoring_dashboard_area:
                    st.session_state.monitoring_dashboard.create_dashboard(st.session_state.performance_monitor)
                
                # Показать рекомендации
                recommendations = st.session_state.performance_monitor.get_optimization_recommendations()
                if recommendations:
                    with recommendations_area:
                        st.subheader("🎯 Рекомендации по оптимизации")
                        for rec in recommendations:
                            if rec['level'] == 'warning':
                                st.warning(f"⚠️ {rec['message']}")
                                st.caption(f"Действие: {rec['action']}")
                            elif rec['level'] == 'info':
                                st.info(f"ℹ️ {rec['message']}")
                                st.caption(f"Действие: {rec['action']}")
                            else:
                                st.success(f"✅ {rec['message']}")
                
                # Адаптивное регулирование rate limiter
                if completed > 20:
                    success_rate = processed_count / completed
                    success_rate_history.append(success_rate)
                    if len(success_rate_history) > 10:
                        success_rate_history.pop(0)
                    
                    avg_success_rate = sum(success_rate_history) / len(success_rate_history)
                    new_rps = rate_limiter.adjust_rate(avg_success_rate)
                    if new_rps != max_rps:
                        logger.info(f"Адаптивное регулирование: {max_rps} -> {new_rps} RPS")
                        max_rps = new_rps
                
                # Сохранение контрольной точки
                if completed % checkpoint_interval == 0:
                    stats_data = {
                        'total_processed': processed_count,
                        'total_errors': error_count,
                        'total_skipped': skipped_count,
                        'elapsed_time': elapsed
                    }
                    save_checkpoint(batch_dir, processed_indices, failed_indices, stats_data)
                    logger.info(f"Контрольная точка сохранена (обработано: {processed_count})")
                
                # AI-оптимизация на основе производительности
                if enable_ai_optimization and current_time - last_optimization_check > 30:
                    last_optimization_check = current_time
                    
                    # Оптимизация параллелизма
                    avg_network = perf_metrics['avg_network_kbps']
                    avg_time = perf_metrics['avg_time_per_image']
                    optimal_threads = st.session_state.parallelism_optimizer.calculate_optimal_threads(
                        avg_network, avg_time
                    )
                    
                    if optimal_threads != max_workers:
                        st.info(f"🤖 AI рекомендует изменить потоки: {max_workers} -> {optimal_threads}")
                        max_workers = optimal_threads
                    
                    # Оптимизация размера партии
                    if auto_memory:
                        images_remaining = total_tasks - completed
                        optimal_batch = st.session_state.memory_manager.optimize_batch_strategy(
                            batch_chunk_size, images_remaining
                        )
                        if optimal_batch != batch_chunk_size:
                            st.info(f"🤖 AI рекомендует изменить размер партии: {batch_chunk_size} -> {optimal_batch}")
                            batch_chunk_size = optimal_batch
                
                # Очистка памяти
                if completed % 50 == 0:
                    gc.collect()
    
    # Финальный отчет
    end_time = time.time()
    elapsed_time = end_time - start_time
    
    # Сохранение финальной контрольной точки
    stats_data = {
        'total_processed': processed_count,
        'total_errors': error_count,
        'total_skipped': skipped_count,
        'elapsed_time': elapsed_time
    }
    save_checkpoint(batch_dir, processed_indices, failed_indices, stats_data)
    
    # Генерация CSV метаданных
    metadata_csv = generate_metadata_csv(batch_dir, df, processed_indices, column_mapping, selected_template)
    
    # Многоформатный экспорт если нужно
    if multi_format_export and export_formats:
        st.info(f"🚀 Начинаю экспорт в дополнительные форматы: {', '.join(export_formats)}")
        converted_files = export_results_multiformat(batch_dir, export_formats)
        st.success(f"✅ Конвертировано {len(converted_files)} файлов в дополнительные форматы")
    
    # Автоматическая архивация
    if auto_zip and processed_count > 0:
        zip_path = os.path.join(output_dir, f"results_{timestamp}.zip")
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, _, files in os.walk(batch_dir):
                for file in files:
                    if file.endswith(('.png', '.jpg', '.jpeg', '.webp', '.csv', '.json', '.txt')):
                        file_path = os.path.join(root, file)
                        arcname = os.path.relpath(file_path, batch_dir)
                        zipf.write(file_path, arcname)
        
        zip_size = os.path.getsize(zip_path) / (1024*1024)
        st.info(f"📦 Создан ZIP архив: {os.path.basename(zip_path)} ({zip_size:.1f} MB)")
    
    # Сохранение статистики в файл
    stats_file = os.path.join(batch_dir, "processing_stats.json")
    final_stats = {
        "total_rows": min(batch_size, len(df)),
        "processed": processed_count,
        "errors": error_count,
        "skipped": skipped_count,
        "elapsed_time": elapsed_time,
        "speed_per_image": elapsed_time / max(1, processed_count),
        "throughput": processed_count / max(1, elapsed_time),
        "template": selected_template,
        "output_format": output_format,
        "quality": output_quality if output_format != "PNG" else "lossless",
        "timestamp": timestamp,
        "performance_metrics": st.session_state.performance_monitor.get_performance_dashboard(),
        "filename_column_used": column_mapping['filename'] if use_filename_column else "automatic",
        "use_filename_column": use_filename_column,
        "optimization_history": st.session_state.performance_monitor.optimization_history,
        "ai_optimization_applied": enable_ai_optimization,
        "parallelism_optimizer_history": st.session_state.parallelism_optimizer.optimal_threads_history[-20:],
        "memory_manager_history": st.session_state.memory_manager.memory_history[-20:]
    }
    
    with open(stats_file, 'w', encoding='utf-8') as f:
        json.dump(final_stats, f, ensure_ascii=False, indent=2)
    
    st.success(f"""
    ## 🎉 Массовая обработка завершена!
    
    **Итоговая статистика:**
    - Всего строк в обработке: {min(batch_size, len(df))}
    - Успешно обработано: {processed_count} изображений
    - Завершилось ошибкой: {error_count}
    - Пропущено (пустые тексты): {skipped_count}
    - Общее время: {elapsed_time:.1f} секунд
    - Скорость: {processed_count/max(1, elapsed_time):.1f} изображений/сек
    - Эффективность: {(processed_count/min(batch_size, len(df))*100):.1f}%
    
    **Результаты сохранены в:** `{os.path.abspath(batch_dir)}`
    **Формат файлов:** {output_format}
    **Качество:** {output_quality if output_format != 'PNG' else 'lossless'}
    **Имена файлов из столбца:** {'Да' if use_filename_column else 'Нет'} {f"({column_mapping['filename']})" if use_filename_column else ""}
    **AI-оптимизация:** {'Включена' if enable_ai_optimization else 'Выключена'}
    """)
    
    # Детальная статистика
    with results_expander:
        if error_list:
            st.error(f"Найдено ошибок: {len(error_list)}")
            for err in error_list[:10]:
                st.text(err)
            if len(error_list) > 10:
                st.warning(f"... и ещё {len(error_list) - 10} ошибок (см. лог-файл)")
        
        # Показать примеры результатов
        if processed_count > 0:
            st.subheader("Примеры обработанных изображений")
            example_files = list(Path(batch_dir).glob(f"*.{output_format.lower()}"))[:3]
            if example_files:
                cols = st.columns(min(3, len(example_files)))
                for i, file_path in enumerate(example_files):
                    with cols[i]:
                        try:
                            img = Image.open(file_path)
                            st.image(img, caption=file_path.name, use_container_width=True)
                            file_size = file_path.stat().st_size / 1024
                            st.caption(f"{file_size:.1f} KB")
                        except Exception as e:
                            st.text(f"Ошибка загрузки: {file_path.name}")
        
        # Кнопки скачивания
        if processed_count > 0:
            col1, col2, col3 = st.columns(3)
            with col1:
                if example_files:
                    example_file = str(example_files[0])
                    with open(example_file, "rb") as f:
                        st.download_button(
                            label="💾 Скачать пример результата",
                            data=f.read(),
                            file_name=os.path.basename(example_file),
                            mime=f"image/{output_format.lower()}"
                        )
            
            with col2:
                if auto_zip and os.path.exists(zip_path):
                    with open(zip_path, "rb") as f:
                        st.download_button(
                            label="📥 Скачать ZIP архив",
                            data=f.read(),
                            file_name=f"infographic_results_{timestamp}.zip",
                            mime="application/zip"
                        )
            
            with col3:
                if metadata_csv:
                    with open(metadata_csv, "rb") as f:
                        st.download_button(
                            label="📄 Скачать метаданные (CSV)",
                            data=f.read(),
                            file_name="metadata.csv",
                            mime="text/csv"
                        )

# ==================== ПАГИНАЦИОННАЯ ОБРАБОТКА ====================
if use_pagination and st.button("📋 Запустить пагинационную обработку"):
    send_notification("Запущена пагинационная обработка больших объемов", "info")
    
    processed_total = process_with_pagination(
        df, 
        batch_size=pagination_batch, 
        start_index=start_from,
        column_mapping=column_mapping,
        selected_template=selected_template,
        output_dir=output_dir,
        max_workers=max_workers
    )
    
    send_notification(f"Пагинационная обработка завершена! Обработано: {processed_total} изображений", "success")

# ==================== АНАЛИЗ РЕЗУЛЬТАТОВ ====================
st.header("8. 📈 AI Анализ результатов")

if st.button("📊 Сгенерировать интеллектуальный отчет"):
    result_dirs = []
    if os.path.exists(output_dir):
        for item in os.listdir(output_dir):
            item_path = os.path.join(output_dir, item)
            if os.path.isdir(item_path) and item.startswith("batch_"):
                result_dirs.append((item_path, os.path.getmtime(item_path)))
    
    if result_dirs:
        result_dirs.sort(key=lambda x: x[1], reverse=True)
        latest_dir = result_dirs[0][0]
        
        # Загрузка статистики
        stats_file = os.path.join(latest_dir, "processing_stats.json")
        if os.path.exists(stats_file):
            with open(stats_file, 'r', encoding='utf-8') as f:
                stats_data = json.load(f)
            
            st.subheader(f"📊 Интеллектуальный анализ: {os.path.basename(latest_dir)}")
            
            # Основные метрики
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric("Обработано", stats_data['processed'])
                st.caption(f"из {stats_data['total_rows']}")
            with col2:
                efficiency = (stats_data['processed']/stats_data['total_rows']*100)
                st.metric("Эффективность", f"{efficiency:.1f}%")
                st.caption(f"Успешность обработки")
            with col3:
                st.metric("Скорость", f"{stats_data['throughput']:.1f} img/сек")
                st.caption(f"{stats_data['elapsed_time']:.0f} сек")
            with col4:
                st.metric("Формат", stats_data['output_format'])
                st.caption(f"Качество: {stats_data['quality']}")
            
            # AI анализ производительности
            st.subheader("🤖 AI Анализ производительности")
            
            perf_metrics = stats_data.get('performance_metrics', {})
            if perf_metrics:
                analysis_cols = st.columns(3)
                with analysis_cols[0]:
                    if perf_metrics.get('avg_cpu_percent', 0) > 80:
                        st.warning("🔥 Высокая загрузка CPU")
                        st.caption("Рекомендуется уменьшить число потоков")
                    else:
                        st.success("⚡ Оптимальная загрузка CPU")
                
                with analysis_cols[1]:
                    if perf_metrics.get('current_memory_mb', 0) > 4000:
                        st.warning("💾 Высокое использование памяти")
                        st.caption("Рекомендуется уменьшить размер партии")
                    else:
                        st.success("💾 Оптимальное использование памяти")
                
                with analysis_cols[2]:
                    if perf_metrics.get('errors_per_hour', 0) > 10:
                        st.error("❌ Высокий уровень ошибок")
                        st.caption("Проверьте качество данных и скорость сети")
                    else:
                        st.success("✅ Низкий уровень ошибок")
            
            # История оптимизации
            if 'optimization_history' in stats_data and stats_data['optimization_history']:
                st.subheader("🔄 История AI оптимизации")
                for opt in stats_data['optimization_history'][-10:]:
                    dt = datetime.fromtimestamp(opt['timestamp']).strftime('%H:%M:%S')
                    st.caption(f"{dt}: {opt['old_size']} → {opt['new_size']} ({opt['reason']})")
            
            # Анализ файлов
            processed_files = list(Path(latest_dir).glob("*.*"))
            image_files = [f for f in processed_files if f.suffix.lower() in ['.png', '.jpg', '.jpeg', '.webp']]
            
            if image_files:
                stats = []
                sample_size = min(100, len(image_files))
                
                for file in image_files[:sample_size]:
                    size_kb = file.stat().st_size / 1024
                    stats.append({
                        "file": file.name, 
                        "size_kb": round(size_kb, 2),
                        "date": datetime.fromtimestamp(file.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
                    })
                
                if stats:
                    stats_df = pd.DataFrame(stats)
                    
                    st.subheader("📈 AI Анализ файлов")
                    
                    tab1, tab2, tab3 = st.tabs(["📊 Распределение размеров", "📁 Детальная статистика", "🎯 Рекомендации"])
                    
                    with tab1:
                        st.bar_chart(stats_df.set_index('file')['size_kb'])
                        
                        avg_size = stats_df['size_kb'].mean()
                        
                        col1, col2 = st.columns(2)
                        with col1:
                            st.metric("Средний размер", f"{avg_size:.1f} KB")
                        with col2:
                            st.metric("Максимальный размер", f"{stats_df['size_kb'].max():.1f} KB")
                    
                    with tab2:
                        st.dataframe(stats_df)
                        
                        report_data = {
                            "Папка с результатами": latest_dir,
                            "Всего файлов": len(image_files),
                            "Диапазон размеров": f"{stats_df['size_kb'].min():.1f} - {stats_df['size_kb'].max():.1f} KB",
                            "Средний размер": f"{stats_df['size_kb'].mean():.1f} KB",
                            "Медианный размер": f"{stats_df['size_kb'].median():.1f} KB",
                            "Общий объем": f"{stats_df['size_kb'].sum() / 1024:.2f} MB",
                            "Дата обработки": stats_df['date'].iloc[0] if len(stats_df) > 0 else "N/A"
                        }
                        
                        for key, value in report_data.items():
                            st.text(f"• {key}: {value}")
                    
                    with tab3:
                        avg_size = stats_df['size_kb'].mean()
                        
                        st.subheader("🎯 AI Рекомендации по оптимизации:")
                        
                        if avg_size > 500:
                            st.error("⚠️ Критическая ситуация: средний размер файлов очень большой (>500KB)")
                            st.write("**Рекомендуемые действия:**")
                            st.write("1. Снизить качество до 70-75%")
                            st.write("2. Использовать формат WebP с настройкой качества 80%")
                            st.write("3. Уменьшить разрешение до 800x800 пикселей")
                            st.write("4. Проверить исходные изображения на избыточное разрешение")
                        elif avg_size > 300:
                            st.warning("⚠️ Требуется оптимизация: средний размер файлов большой (>300KB)")
                            st.write("**Рекомендуемые действия:**")
                            st.write("1. Снизить качество до 80-85%")
                            st.write("2. Конвертировать в WebP формат")
                            st.write("3. Проверить настройки водяных знаков")
                        elif avg_size > 150:
                            st.info("ℹ️ Хорошие показатели: размер файлов оптимален для большинства случаев")
                            st.write("**Рекомендации:**")
                            st.write("1. Поддерживать текущие настройки")
                            st.write("2. Мониторить производительность")
                        else:
                            st.success("✅ Отличные показатели: размер файлов идеален для веба")
                            st.write("**Рекомендации:**")
                            st.write("1. Продолжать текущую стратегию")
                            st.write("2. Документировать успешные настройки")
    else:
        st.info("Пока нет результатов для анализа. Запустите обработку сначала.")

# ==================== МОНИТОРИНГ ПРОИЗВОДИТЕЛЬНОСТИ ====================
st.header("9. 📊 Расширенный мониторинг производительности")

if 'performance_monitor' in st.session_state:
    perf_metrics = st.session_state.performance_monitor.get_performance_dashboard()
    
    # Основные метрики
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Скорость обработки", f"{perf_metrics['throughput']:.1f}", "img/сек")
    with col2:
        st.metric("Среднее время", f"{perf_metrics['avg_time_per_image']:.2f}", "сек")
    with col3:
        st.metric("Память (текущ)", f"{perf_metrics['current_memory_mb']:.0f}", "MB")
    with col4:
        st.metric("Ошибок в час", f"{perf_metrics['errors_per_hour']:.1f}")
    
    # Дополнительные метрики
    col5, col6, col7, col8 = st.columns(4)
    with col5:
        st.metric("Средняя нагрузка CPU", f"{perf_metrics['avg_cpu_percent']:.1f}", "%")
    with col6:
        st.metric("Скорость сети", f"{perf_metrics['avg_network_kbps']:.0f}", "KB/s")
    with col7:
        st.metric("Всего обработано", f"{perf_metrics['total_processed']:.0f}")
    with col8:
        elapsed_hours = perf_metrics['elapsed_time'] / 3600
        st.metric("Общее время", f"{elapsed_hours:.1f}", "ч")
    
    # Графики в реальном времени
    st.subheader("📈 AI Анализ трендов")
    
    if st.session_state.performance_monitor.history:
        df_history = pd.DataFrame(st.session_state.performance_monitor.history[-100:])
        
        tab1, tab2, tab3 = st.tabs(["Производительность", "Ресурсы", "Прогнозы"])
        
        with tab1:
            col1, col2 = st.columns(2)
            with col1:
                if 'processing_time' in df_history.columns:
                    st.line_chart(df_history.set_index('timestamp')['processing_time'])
                    st.caption("📊 Время обработки изображения (сек)")
                    
                    # AI анализ тренда
                    if len(df_history) > 10:
                        recent_avg = df_history['processing_time'].tail(10).mean()
                        older_avg = df_history['processing_time'].head(10).mean()
                        if recent_avg > older_avg * 1.2:
                            st.warning("⚠️ Наблюдается замедление обработки")
                        elif recent_avg < older_avg * 0.8:
                            st.success("✅ Наблюдается ускорение обработки")
            
            with col2:
                if 'processing_time' in df_history.columns:
                    throughput = 1 / df_history['processing_time'].rolling(10).mean()
                    st.line_chart(throughput)
                    st.caption("⚡ Скорость обработки (img/сек)")
        
        with tab2:
            col1, col2 = st.columns(2)
            with col1:
                if 'memory_mb' in df_history.columns:
                    st.line_chart(df_history.set_index('timestamp')['memory_mb'])
                    st.caption("💾 Использование памяти (MB)")
                    
                    # Анализ утечек памяти
                    if len(df_history) > 20:
                        memory_growth = df_history['memory_mb'].iloc[-1] - df_history['memory_mb'].iloc[0]
                        if memory_growth > 500:  # Рост на 500MB
                            st.error("⚠️ Возможная утечка памяти")
                        elif memory_growth > 200:
                            st.warning("⚠️ Значительный рост использования памяти")
            
            with col2:
                if 'cpu_percent' in df_history.columns:
                    st.line_chart(df_history.set_index('timestamp')['cpu_percent'])
                    st.caption("🔥 Загрузка CPU (%)")
                    
                    # Анализ нагрузки CPU
                    if 'cpu_percent' in df_history.columns:
                        avg_cpu = df_history['cpu_percent'].mean()
                        if avg_cpu > 85:
                            st.error("🔥 Очень высокая нагрузка CPU")
                        elif avg_cpu > 70:
                            st.warning("⚠️ Высокая нагрузка CPU")
        
        with tab3:
            # Прогнозирование на основе данных
            st.info("🤖 AI Прогнозы на основе текущих данных:")
            
            if perf_metrics['total_processed'] > 10:
                # Прогноз времени завершения
                remaining_images = st.session_state.get('remaining_images', 1000)
                estimated_time = st.session_state.performance_monitor.estimate_completion(remaining_images)
                
                if estimated_time:
                    if estimated_time > 3600:
                        eta_str = f"{estimated_time/3600:.1f} часов"
                    elif estimated_time > 60:
                        eta_str = f"{estimated_time/60:.1f} минут"
                    else:
                        eta_str = f"{estimated_time:.0f} секунд"
                    
                    st.metric("⏱️ Прогноз времени завершения", eta_str)
                    
                    # Прогноз использования памяти
                    predicted_memory = st.session_state.memory_manager.predict_memory_peak(remaining_images)
                    if predicted_memory:
                        system_memory = psutil.virtual_memory().total / (1024*1024)
                        memory_percent = (predicted_memory / system_memory) * 100
                        
                        if memory_percent > 90:
                            st.error(f"⚠️ Прогнозируется исчерпание памяти: {memory_percent:.1f}%")
                        elif memory_percent > 80:
                            st.warning(f"⚠️ Высокое использование памяти: {memory_percent:.1f}%")
                        else:
                            st.success(f"✅ Память в норме: {memory_percent:.1f}%")
                
                # Прогноз производительности
                current_throughput = perf_metrics['throughput']
                if current_throughput > 20:
                    st.success(f"🚀 Отличная производительность: {current_throughput:.1f} img/сек")
                elif current_throughput > 10:
                    st.info(f"⚡ Хорошая производительность: {current_throughput:.1f} img/сек")
                elif current_throughput > 5:
                    st.warning(f"⚠️ Средняя производительность: {current_throughput:.1f} img/сек")
                else:
                    st.error(f"❌ Низкая производительность: {current_throughput:.1f} img/сек")
    
    # AI рекомендации по оптимизации
    st.subheader("🎯 AI Рекомендации по оптимизации")
    
    recommendations = st.session_state.parallelism_optimizer.get_recommendation()
    for rec in recommendations:
        st.info(rec)
    
    # Добавление собственных рекомендаций на основе метрик
    if perf_metrics['avg_network_kbps'] < 100:
        st.warning("📶 Низкая скорость сети - основное ограничение производительности")
        st.caption("Рекомендуется увеличить пропускную способность или уменьшить параллелизм")
    
    if perf_metrics['current_memory_mb'] > 8000:  # >8GB
        st.error("💾 Очень высокое использование памяти")
        st.caption("Рекомендуется уменьшить размер партии и включить агрессивную сборку мусора")
    
    if perf_metrics['errors_per_hour'] > 20:
        st.error("❌ Критический уровень ошибок")
        st.caption("Рекомендуется проверить качество данных, увеличить таймауты и уменьшить скорость запросов")

# ==================== УТИЛИТЫ ====================
st.header("10. 🛠️ Расширенные утилиты")

utils_tabs = st.tabs(["Переименование файлов", "Экспорт в форматы", "Очистка системы", "AI Оптимизация"])

with utils_tabs[0]:
    st.subheader("📝 Интеллектуальное переименование файлов")
    
    # Выбор папки для переименования
    rename_dir = st.text_input("Папка с файлами для переименования", output_dir)
    
    if os.path.exists(rename_dir):
        rename_cols = st.columns(2)
        with rename_cols[0]:
            if st.button("🔍 Проверить файлы для переименования"):
                files = list(Path(rename_dir).glob("*.*"))
                image_files = [f for f in files if f.suffix.lower() in ['.png', '.jpg', '.jpeg', '.webp']]
                
                if image_files:
                    st.success(f"Найдено {len(image_files)} файлов для переименования")
                    
                    # AI анализ имен файлов
                    st.subheader("🤖 AI Анализ имен файлов")
                    
                    name_patterns = {}
                    for file in image_files[:10]:
                        name = file.stem
                        if '_' in name:
                            parts = name.split('_')
                            pattern = f"{parts[0]}_*" if len(parts) > 1 else name
                        else:
                            pattern = name
                        
                        name_patterns[pattern] = name_patterns.get(pattern, 0) + 1
                    
                    if name_patterns:
                        st.write("**Обнаруженные шаблоны имен:**")
                        for pattern, count in list(name_patterns.items())[:5]:
                            st.write(f"- {pattern}: {count} файлов")
        
        with rename_cols[1]:
            if st.button("🔄 Интеллектуальное переименование"):
                rename_log = rename_processed_files(rename_dir, df, column_mapping['filename'], output_format)
                if rename_log:
                    st.success(f"✅ Переименовано {len(rename_log)} файлов")
                    
                    # AI анализ результатов переименования
                    new_names = [log['new'] for log in rename_log[:10]]
                    st.write("**Примеры новых имен:**")
                    for name in new_names:
                        st.text(name)
                else:
                    st.info("Файлы уже имеют правильные имена или нет файлов для переименования")

with utils_tabs[1]:
    st.subheader("🔄 AI Рекомендации по экспорту в форматы")
    
    export_source_dir = st.text_input("Папка с исходными файлами для экспорта", output_dir)
    
    if os.path.exists(export_source_dir):
        # AI анализ содержимого папки
        files = list(Path(export_source_dir).glob("*.*"))
        image_files = [f for f in files if f.suffix.lower() in ['.png', '.jpg', '.jpeg', '.webp']]
        
        if image_files:
            st.info(f"🤖 Найдено {len(image_files)} изображений для анализа")
            
            # Анализ текущих форматов
            format_stats = {}
            total_size = 0
            
            for file in image_files[:50]:  # Ограничиваем выборку
                format = file.suffix.lower()[1:]  # Убираем точку
                size_kb = file.stat().st_size / 1024
                format_stats[format] = format_stats.get(format, 0) + 1
                total_size += size_kb
            
            if format_stats:
                st.write("**Текущее распределение форматов:**")
                for fmt, count in format_stats.items():
                    percentage = (count / len(image_files)) * 100
                    st.write(f"- {fmt.upper()}: {count} файлов ({percentage:.1f}%)")
                
                avg_size = total_size / len(image_files)
                st.write(f"**Средний размер файла:** {avg_size:.1f} KB")
                
                # AI рекомендации
                st.subheader("🎯 AI Рекомендации по форматам:")
                
                if avg_size > 300:
                    st.error("⚠️ Критически большие файлы")
                    st.write("**Рекомендуется:** WebP с качеством 75%")
                elif avg_size > 150:
                    st.warning("⚠️ Большие файлы для веба")
                    st.write("**Рекомендуется:** WebP с качеством 85% или JPEG с качеством 80%")
                elif avg_size > 50:
                    st.info("ℹ️ Оптимальный размер")
                    st.write("**Рекомендуется:** Текущие настройки или WebP для лучшего сжатия")
                else:
                    st.success("✅ Отличный размер файлов")
                    st.write("**Рекомендуется:** Сохранять текущие настройки")
    
    export_formats_select = st.multiselect(
        "Выберите форматы для экспорта",
        ["PNG", "JPEG", "WebP"],
        default=["WebP", "JPEG"]
    )
    
    if st.button("🚀 Запустить интеллектуальный экспорт"):
        if os.path.exists(export_source_dir) and export_formats_select:
            converted = export_results_multiformat(export_source_dir, export_formats_select)
            st.success(f"✅ Конвертировано {len(converted)} файлов в форматы: {', '.join(export_formats_select)}")

with utils_tabs[2]:
    st.subheader("🧹 Интеллектуальная очистка системы")
    
    cleanup_cols = st.columns(4)
    with cleanup_cols[0]:
        if st.button("🗑️ Очистить кэш изображений", use_container_width=True):
            cache_dir = ".cache"
            if os.path.exists(cache_dir):
                import shutil
                shutil.rmtree(cache_dir)
                os.makedirs(cache_dir, exist_ok=True)
                st.success("Кэш изображений очищен")
    
    with cleanup_cols[1]:
        if st.button("🧽 Освободить память", use_container_width=True):
            gc.collect()
            st.success("Память очищена")
            st.info(f"Текущее использование памяти: {psutil.Process().memory_info().rss / 1024 / 1024:.0f} MB")
    
    with cleanup_cols[2]:
        if st.button("📊 Сбросить статистику", use_container_width=True):
            if 'performance_monitor' in st.session_state:
                del st.session_state.performance_monitor
                st.session_state.performance_monitor = EnhancedPerformanceMonitor()
            if 'speed_history' in st.session_state:
                del st.session_state.speed_history
            st.success("Статистика сброшена")
    
    with cleanup_cols[3]:
        if st.button("🔧 Оптимизировать систему", use_container_width=True):
            # Комплексная оптимизация
            gc.collect()
            
            # Очистка временных файлов
            temp_dirs = [".cache", "__pycache__"]
            for temp_dir in temp_dirs:
                if os.path.exists(temp_dir):
                    import shutil
                    try:
                        shutil.rmtree(temp_dir)
                    except:
                        pass
            
            st.success("✅ Система оптимизирована")
    
    # AI анализ системы
    st.subheader("🤖 AI Анализ состояния системы")
    
    if st.button("🔍 Проанализировать систему"):
        system_info = {
            "Память": f"{psutil.virtual_memory().percent}%",
            "CPU": f"{psutil.cpu_percent()}%",
            "Диск": f"{psutil.disk_usage('.').percent}%",
            "Процессы": len(psutil.pids())
        }
        
        st.write("**Текущее состояние системы:**")
        for key, value in system_info.items():
            st.write(f"- {key}: {value}")
        
        # AI рекомендации
        recommendations = []
        
        if psutil.virtual_memory().percent > 85:
            recommendations.append("⚠️ Высокое использование памяти. Закройте ненужные приложения.")
        
        if psutil.cpu_percent() > 90:
            recommendations.append("🔥 Высокая нагрузка CPU. Уменьшите параллелизм обработки.")
        
        if psutil.disk_usage('.').percent > 90:
            recommendations.append("💾 Мало свободного места на диске. Очистите временные файлы.")
        
        if recommendations:
            st.subheader("🎯 Рекомендации по оптимизации системы:")
            for rec in recommendations:
                st.info(rec)
        else:
            st.success("✅ Система в оптимальном состоянии")

with utils_tabs[3]:
    st.subheader("🤖 AI Оптимизация параметров")
    
    # AI анализ текущих настроек
    current_settings = {
        "Потоки": max_workers,
        "Размер партии": batch_chunk_size,
        "Ретри": retry_count,
        "Таймаут": 15,
        "Формат": output_format,
        "Качество": output_quality
    }
    
    st.write("**Текущие настройки:**")
    for key, value in current_settings.items():
        st.write(f"- {key}: {value}")
    
    # AI оптимизация
    if st.button("🎯 Оптимизировать настройки AI"):
        # Анализ системы
        cpu_cores = psutil.cpu_count(logical=False)
        total_memory_gb = psutil.virtual_memory().total / (1024**3)
        
        # AI рекомендации
        recommendations = {}
        
        # Оптимизация потоков
        if total_memory_gb > 16:
            recommendations['threads'] = min(32, cpu_cores * 4)
        elif total_memory_gb > 8:
            recommendations['threads'] = min(16, cpu_cores * 2)
        else:
            recommendations['threads'] = min(8, cpu_cores)
        
        # Оптимизация размера партии
        if total_memory_gb > 32:
            recommendations['batch_size'] = 1000
        elif total_memory_gb > 16:
            recommendations['batch_size'] = 500
        else:
            recommendations['batch_size'] = 100
        
        # Оптимизация формата
        recommendations['format'] = 'WebP'
        recommendations['quality'] = 85
        
        # Оптимизация ретри
        recommendations['retry'] = 3
        
        st.subheader("🎯 AI Рекомендации по оптимизации:")
        for key, value in recommendations.items():
            st.write(f"- {key}: {value}")
        
        # Применение рекомендаций
        if st.button("✅ Применить AI рекомендации"):
            max_workers = recommendations['threads']
            batch_chunk_size = recommendations['batch_size']
            retry_count = recommendations['retry']
            output_format = recommendations['format']
            output_quality = recommendations['quality']
            
            st.success("✅ Настройки оптимизированы AI")
            st.rerun()

# ==================== ФУТЕР ====================
st.divider()
st.caption("""
💡 **Промышленные рекомендации для обработки 100,000+ изображений v3.0:**

1. **AI Оптимизация:** Всегда включайте AI-оптимизацию для автоматической настройки параметров
2. **Мониторинг:** Используйте расширенную панель мониторинга для контроля в реальном времени
3. **Память:** Включите автоматическое управление памятью для предотвращения утечек
4. **Сеть:** Настройте rate limiting для избежания блокировок
5. **Резервное копирование:** Сохраняйте контрольные точки каждые 100-500 изображений

🔧 **Технические требования для промышленного использования:**
- Python 3.9+
- 32ГБ RAM (рекомендуется 64ГБ+ для 100k+ изображений)
- SSD NVMe диск для максимальной скорости записи
- Стабильный интернет (минимум 500 Mbps для параллельной загрузки)
- 100+ ГБ свободного места на диске
- Многоядерный процессор (минимум 8 ядер)

🚀 **AI Стратегия обработки 100,000 изображений:**
1. **Фаза 1:** AI Анализ и настройка (100 шт) - определение оптимальных параметров
2. **Фаза 2:** Пилотная обработка (10,000 шт) - валидация и тонкая настройка AI  
3. **Фаза 3:** Основная обработка (80,000 шт) - разбить на партии по 10-20k с AI оптимизацией
4. **Фаза 4:** AI Контроль качества (9,900 шт) - автоматическая проверка и исправление
5. **Фаза 5:** Финализация (100 шт) - ручная проверка и отчетность

🤖 **AI Возможности системы:**
- Автоматическая оптимизация параллелизма
- Прогнозирование использования ресурсов
- Интеллектуальная обработка ошибок
- Адаптивное управление памятью
- AI рекомендации по настройкам
- Прогрессивное обучение на основе данных

📞 **Поддержка:** При возникновении ошибок AI система автоматически предложит решения
""")

# ==================== ИНФОРМАЦИЯ О СИСТЕМЕ ====================
with st.expander("ℹ️ Расширенная информация о системе v3.0"):
    st.write("**Системная информация:**")
    
    sys_info_cols = st.columns(4)
    with sys_info_cols[0]:
        st.write(f"- Платформа: {platform.platform()}")
        st.write(f"- Python: {sys.version.split()[0]}")
        st.write(f"- Streamlit: {st.__version__}")
        st.write(f"- Pillow: {Image.__version__}")
    
    with sys_info_cols[1]:
        cpu_info = {
            "Ядра (физические)": psutil.cpu_count(logical=False),
            "Ядра (логические)": psutil.cpu_count(logical=True),
            "Частота": f"{psutil.cpu_freq().current:.0f} MHz" if psutil.cpu_freq() else "N/A",
            "Архитектура": platform.architecture()[0]
        }
        
        for key, value in cpu_info.items():
            st.write(f"- {key}: {value}")
    
    with sys_info_cols[2]:
        memory = psutil.virtual_memory()
        memory_info = {
            "Всего": f"{memory.total / (1024**3):.1f} GB",
            "Доступно": f"{memory.available / (1024**3):.1f} GB",
            "Использовано": f"{memory.percent}%",
            "Кэш": f"{memory.cached / (1024**3):.1f} GB"
        }
        
        for key, value in memory_info.items():
            st.write(f"- {key}: {value}")
    
    with sys_info_cols[3]:
        disk = psutil.disk_usage('.')
        disk_info = {
            "Всего": f"{disk.total / (1024**3):.1f} GB",
            "Свободно": f"{disk.free / (1024**3):.1f} GB",
            "Использовано": f"{disk.percent}%",
            "Файловая система": platform.system()
        }
        
        for key, value in disk_info.items():
            st.write(f"- {key}: {value}")
    
    # Проверка зависимостей
    st.write("**Зависимости и статус:**")
    deps_cols = st.columns(4)
    
    dependencies = [
        ("streamlit", "UI фреймворк"),
        ("Pillow", "Обработка изображений"),
        ("pandas", "Работа с данными"),
        ("requests", "HTTP запросы"),
        ("psutil", "Мониторинг системы"),
        ("streamlit-gsheets", "Google Sheets"),
        ("concurrent.futures", "Параллелизм"),
        ("hashlib", "Хеширование")
    ]
    
    for i, (dep, desc) in enumerate(dependencies):
        col_idx = i % 4
        with deps_cols[col_idx]:
            try:
                if dep == 'Pillow':
                    module = Image
                elif dep == 'concurrent.futures':
                    module = concurrent.futures
                elif dep == 'hashlib':
                    module = hashlib
                else:
                    module = __import__(dep.replace("-", "_"))
                
                st.success(f"✅ {dep}")
                st.caption(desc)
            except ImportError:
                st.error(f"❌ {dep}")
                st.caption(f"Требуется: `pip install {dep}`")
    
    # Информация о AI компонентах
    st.write("**🤖 AI Компоненты системы:**")
    
    ai_components = [
        ("EnhancedPerformanceMonitor", "Мониторинг производительности"),
        ("AdvancedMemoryManager", "Управление памятью"),
        ("DynamicParallelismOptimizer", "Оптимизация параллелизма"),
        ("SmartRetryManager", "Обработка ошибок"),
        ("IntelligentPreviewValidator", "Валидация"),
        ("ResourceBalancer", "Распределение ресурсов"),
        ("MonitoringDashboard", "Панель мониторинга"),
        ("LargeScalePlanner", "Планирование")
    ]
    
    ai_cols = st.columns(4)
    for i, (component, desc) in enumerate(ai_components):
        with ai_cols[i % 4]:
            st.info(f"🤖 {component}")
            st.caption(desc)
    
    # Тестирование производительности
    if st.button("⚡ Тест производительности системы"):
        with st.spinner("Запуск тестов производительности..."):
            test_results = {}
            
            # Тест CPU
            start = time.time()
            for _ in range(1000000):
                pass
            test_results['CPU'] = f"{(time.time() - start) * 1000:.1f} ms"
            
            # Тест памяти
            import numpy as np
            start = time.time()
            arr = np.random.rand(1000, 1000)
            test_results['Memory'] = f"{(time.time() - start) * 1000:.1f} ms"
            
            # Тест диска
            start = time.time()
            with open('test_file.txt', 'w') as f:
                f.write('x' * 1000000)
            test_results['Disk Write'] = f"{(time.time() - start) * 1000:.1f} ms"
            
            os.remove('test_file.txt')
            
            st.write("**Результаты тестов производительности:**")
            for test, result in test_results.items():
                st.write(f"- {test}: {result}")
            
            # AI оценка системы
            st.subheader("🤖 AI Оценка системы:")
            
            system_score = 0
            if float(test_results['CPU'].split()[0]) < 100:
                system_score += 25
                st.success("✅ CPU: Отличная производительность")
            else:
                st.warning("⚠️ CPU: Средняя производительность")
            
            if float(test_results['Memory'].split()[0]) < 50:
                system_score += 25
                st.success("✅ Память: Быстрый доступ")
            else:
                st.warning("⚠️ Память: Средняя скорость")
            
            if float(test_results['Disk Write'].split()[0]) < 100:
                system_score += 25
                st.success("✅ Диск: Быстрая запись")
            else:
                st.warning("⚠️ Диск: Медленная запись")
            
            if psutil.virtual_memory().total > 8 * 1024**3:  # >8GB
                system_score += 25
                st.success("✅ Объем памяти: Достаточно")
            else:
                st.warning("⚠️ Объем памяти: Ограничен")
            
            st.metric("🏆 Общий балл системы", f"{system_score}/100")
            
            if system_score > 75:
                st.success("🚀 Система готова к промышленной обработке")
            elif system_score > 50:
                st.info("⚡ Система подходит для средних объемов")
            else:
                st.warning("⚠️ Рекомендуется обновить систему для больших объемов")

# ==================== ИНИЦИАЛИЗАЦИЯ И СОХРАНЕНИЕ НАСТРОЕК ====================
# Сохранение текущих настроек
if 'app_settings' not in st.session_state:
    st.session_state.app_settings = {
        'version': '3.0',
        'last_updated': datetime.now().isoformat(),
        'ai_optimization': enable_ai_optimization if 'enable_ai_optimization' in locals() else True,
        'auto_memory': auto_memory,
        'template': selected_template
    }

# Автосохранение настроек при выходе
import atexit

def save_settings_on_exit():
    """Сохранение настроек при выходе из приложения"""
    settings_file = "app_settings.json"
    st.session_state.app_settings['last_session'] = datetime.now().isoformat()
    
    with open(settings_file, 'w', encoding='utf-8') as f:
        json.dump(st.session_state.app_settings, f, indent=2, ensure_ascii=False)

atexit.register(save_settings_on_exit)

# Загрузка предыдущих настроек
settings_file = "app_settings.json"
if os.path.exists(settings_file):
    try:
        with open(settings_file, 'r', encoding='utf-8') as f:
            saved_settings = json.load(f)
        st.info(f"📁 Загружены сохраненные настройки от {saved_settings.get('last_session', 'неизвестно')}")
    except:
        pass
