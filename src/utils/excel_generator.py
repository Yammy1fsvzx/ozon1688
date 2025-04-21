#!/usr/bin/env python
# -*- coding: utf-8 -*-

import pandas as pd
from datetime import datetime
from src.core.database import Database
from src.core.models import ProductProfitability, OzonProduct, AlibabaProduct, Task, MatchedProduct
from sqlalchemy import desc
from src.utils.logger import logger

class ExcelGenerator:
    def __init__(self):
        self.db = Database()
    
    def generate_report(self, tasks: list) -> str:
        """
        Генерирует отчет по задачам пользователя в формате Excel
        
        :param tasks: Список задач пользователя
        :return: Путь к сгенерированному файлу
        """
        try:
            logger.info(f"Начало генерации отчета для {len(tasks)} задач")
            logger.debug(f"Полученные задачи: {tasks}")
            
            # Получаем сессию базы данных
            session = self.db.get_session()
            
            # Получаем список ID задач
            task_ids = [task['id'] for task in tasks]
            logger.debug(f"ID задач для отчета: {task_ids}")
            
            # Формируем запрос через SQLAlchemy
            query = session.query(
                OzonProduct.product_name.label('Товар'),
                OzonProduct.url.label('Ссылка OZON'),
                AlibabaProduct.url.label('_Ссылка 1688_'), # Временное имя, скрытое от пользователя
                ProductProfitability.selling_price.label('Цена продажи'),
                AlibabaProduct.price_usd.label('Цена покупки'),
                ProductProfitability.marketplace_commission.label('Комиссия МП'),
                ProductProfitability.taxes.label('Налоги'),
                OzonProduct.weight.label('Вес товара'),
                OzonProduct.dimensions.label('Объем упаковки'),
                ProductProfitability.delivery_cost.label('Доставка России'),
                ProductProfitability.packaging_cost.label('Расходные материалы'),
                ProductProfitability.agent_commission.label('Комиссия агента'),
                ProductProfitability.total_profit.label('Итого'),
                ProductProfitability.profitability_percent.label('Маржинальность %'),
                Task.status.label('Статус'),
                Task.created_at.label('Дата добавления')
            ).join(
                Task,
                Task.id == OzonProduct.task_id
            ).outerjoin(
                MatchedProduct,
                MatchedProduct.ozon_product_id == OzonProduct.id
            ).outerjoin(
                AlibabaProduct,
                MatchedProduct.alibaba_product_id == AlibabaProduct.id
            ).outerjoin(
                ProductProfitability,
                ProductProfitability.match_id == MatchedProduct.id
            ).filter(
                Task.id.in_(task_ids)
            ).order_by(
                Task.created_at.desc()
            )
            
            # Получаем результаты
            results = query.all()
            logger.debug(f"Получено {len(results)} результатов из базы данных")
            
            # Преобразуем результаты в DataFrame
            data = []
            for row in results:
                row_dict = {}
                for column, value in row._mapping.items():
                    # Заменяем пустые значения на "Н/Д"
                    if value is None or (isinstance(value, (int, float)) and value == 0):
                        row_dict[column] = "Н/Д"
                    else:
                        row_dict[column] = value
                data.append(row_dict)
            
            df = pd.DataFrame(data)
            logger.debug(f"Создан DataFrame с {len(df)} строками")
            
            # Форматируем числовые значения
            numeric_columns = [
                'Цена продажи', 'Цена покупки', 'Комиссия МП', 'Налоги',
                'Вес товара', 'Доставка России', 'Расходные материалы',
                'Комиссия агента', 'Итого', 'Маржинальность %'
            ]
            
            for col in numeric_columns:
                if col in df.columns:
                    if col == 'Маржинальность %':
                        # Обрабатываем только непустые значения
                        df[col] = df[col].apply(lambda x: f"{float(x):.2f}%" if x != "Н/Д" else "Н/Д")
                    else:
                        # Обрабатываем только непустые значения
                        df[col] = df[col].apply(lambda x: f"{float(x):.2f}" if x != "Н/Д" else "Н/Д")
            
            # Форматируем статусы
            status_emojis = {
                'pending': '⏳',
                'ozon_processed': '🔄',
                'completed': '✅',
                'error': '❌',
                'fatal': '💥',
                'not_found': '🔍',
                'failed': '⚠️'
            }
            df['Статус'] = df['Статус'].apply(lambda x: status_emojis.get(x, '•'))
            
            # Форматируем даты
            df['Дата добавления'] = df['Дата добавления'].apply(lambda x: x.strftime('%d.%m.%Y %H:%M') if x != "Н/Д" else "Н/Д")
            
            # Генерируем имя файла с текущей датой и временем
            filename = f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
            
            # Создаем Excel файл
            with pd.ExcelWriter(filename, engine='xlsxwriter') as writer:
                # Удаляем колонку со ссылкой на 1688 перед записью в Excel
                df_for_excel = df.drop(columns=['_Ссылка 1688_'])
                
                # Записываем данные
                df_for_excel.to_excel(writer, sheet_name='Отчет', index=False)
                
                # Получаем объект рабочей книги и листа
                workbook = writer.book
                worksheet = writer.sheets['Отчет']
                
                # Форматирование заголовков
                header_format = workbook.add_format({
                    'bold': True,
                    'bg_color': '#4B0082',
                    'font_color': 'white',
                    'border': 1,
                    'text_wrap': True,
                    'align': 'center',
                    'valign': 'vcenter'
                })
                
                # Формат для ссылок
                link_format = workbook.add_format({
                    'font_color': 'blue',
                    'underline': True,
                    'align': 'center',
                    'valign': 'vcenter',
                    'text_wrap': True
                })
                
                # Формат для чисел
                number_format = workbook.add_format({
                    'num_format': '#,##0.00',
                    'align': 'center',
                    'valign': 'vcenter'
                })
                
                # Формат для процентов
                percent_format = workbook.add_format({
                    'num_format': '0.00%',
                    'align': 'center',
                    'valign': 'vcenter'
                })
                
                # Формат для обычного текста
                text_format = workbook.add_format({
                    'align': 'center',
                    'valign': 'vcenter',
                    'text_wrap': True
                })
                
                # Применяем форматирование к заголовкам
                for col_num, value in enumerate(df_for_excel.columns.values):
                    worksheet.write(0, col_num, value, header_format)
                    
                    # Устанавливаем ширину столбцов
                    if value in ['Товар']:
                        worksheet.set_column(col_num, col_num, 40)
                    elif value in ['Ссылка OZON']:
                        worksheet.set_column(col_num, col_num, 50)
                    elif value in ['Объем упаковки', 'Статус']:
                        worksheet.set_column(col_num, col_num, 20)
                    elif value == 'Дата добавления':
                        worksheet.set_column(col_num, col_num, 25)
                    else:
                        worksheet.set_column(col_num, col_num, 15)
                
                # Добавляем ссылки и форматируем данные
                for row_num in range(1, len(df) + 1):
                    # Название товара как ссылка на 1688
                    product_name = df.iloc[row_num-1]['Товар']
                    alibaba_url = df.iloc[row_num-1]['_Ссылка 1688_']
                    # Проверяем, что ссылка не "Н/Д"
                    if alibaba_url != "Н/Д":
                        worksheet.write_url(row_num, 0, alibaba_url, link_format, product_name)
                    else:
                        worksheet.write(row_num, 0, product_name, text_format)
                    
                    # Ссылка на OZON
                    ozon_url = df.iloc[row_num-1]['Ссылка OZON']
                    worksheet.write_url(row_num, 1, ozon_url, link_format)
                    
                    # Форматируем числовые значения и остальные поля
                    for col_num, col_name in enumerate(df_for_excel.columns):
                        value = df_for_excel.iloc[row_num-1][col_name]
                        if col_name in numeric_columns:
                            if value != "Н/Д":
                                if col_name == 'Маржинальность %':
                                    worksheet.write(row_num, col_num, float(value.rstrip('%')) / 100, percent_format)
                                else:
                                    worksheet.write(row_num, col_num, float(value), number_format)
                            else:
                                worksheet.write(row_num, col_num, value, text_format)
                        elif col_name not in ['Товар', 'Ссылка OZON']:
                            worksheet.write(row_num, col_num, value, text_format)
                
                # Замораживаем первую строку
                worksheet.freeze_panes(1, 0)
                
                # Устанавливаем высоту строк
                worksheet.set_default_row(30)
            
            logger.info(f"Отчет успешно сгенерирован: {filename}")
            return filename
            
        except Exception as e:
            logger.error(f"Ошибка при генерации отчета: {str(e)}")
            return None
        finally:
            if session:
                session.close() 