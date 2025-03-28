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
    
    def generate_profitability_report(self) -> str:
        """
        Генерирует отчет по прибыльности товаров в формате Excel
        
        :return: Путь к сгенерированному файлу
        """
        try:
            # Получаем сессию базы данных
            session = self.db.get_session()
            
            # Формируем запрос через SQLAlchemy
            query = session.query(
                OzonProduct.product_name.label('Товар'),
                OzonProduct.url.label('Ссылка OZON'),
                AlibabaProduct.url.label('Ссылка 1688'),
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
                ProductProfitability.profitability_percent.label('Маржинальность %')
            ).join(
                MatchedProduct,
                MatchedProduct.ozon_product_id == OzonProduct.id
            ).join(
                AlibabaProduct,
                MatchedProduct.alibaba_product_id == AlibabaProduct.id
            ).join(
                ProductProfitability,
                ProductProfitability.match_id == MatchedProduct.id
            ).order_by(
                ProductProfitability.created_at
            )
            
            # Получаем результаты
            results = query.all()
            
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
            
            # Генерируем имя файла с текущей датой и временем
            filename = f"profitability_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
            
            # Создаем Excel файл
            with pd.ExcelWriter(filename, engine='xlsxwriter') as writer:
                # Записываем данные
                df.to_excel(writer, sheet_name='Прибыльность', index=False)
                
                # Получаем объект рабочей книги и листа
                workbook = writer.book
                worksheet = writer.sheets['Прибыльность']
                
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
                for col_num, value in enumerate(df.columns.values):
                    worksheet.write(0, col_num, value, header_format)
                    
                    # Устанавливаем ширину столбцов
                    if value in ['Товар']:
                        worksheet.set_column(col_num, col_num, 40)
                    elif value in ['Ссылка OZON']:
                        worksheet.set_column(col_num, col_num, 50)
                    elif value in ['Объем упаковки']:
                        worksheet.set_column(col_num, col_num, 20)
                    else:
                        worksheet.set_column(col_num, col_num, 15)
                
                # Добавляем ссылки и форматируем данные
                for row_num in range(1, len(df) + 1):
                    # Название товара OZON как ссылка на 1688
                    product_name = df.iloc[row_num-1]['Товар']
                    alibaba_url = df.iloc[row_num-1]['Ссылка 1688']
                    worksheet.write_url(row_num, 0, alibaba_url, link_format, product_name)
                    
                    # Ссылка на OZON
                    ozon_url = df.iloc[row_num-1]['Ссылка OZON']
                    worksheet.write_url(row_num, 1, ozon_url, link_format)
                    
                    # Форматируем числовые значения и остальные поля
                    for col_num, col_name in enumerate(df.columns):
                        value = df.iloc[row_num-1][col_name]
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