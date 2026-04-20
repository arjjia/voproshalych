# Инкрементальное наполнение Базы Знаний

Справочник документов и страниц для точечной индексации через `--url`.

## Использование

```bash
# Добавить документ (если уже в БД — пропустит)
docker compose exec qa-service uv run python scripts/fill_kb_unified.py --url "<URL>"

# Добавить несколько документов
python scripts/fill_kb_unified.py \
  --url "<URL_1>" \
  --url "<URL_2>"

# Переиндексировать (удалить старый + вставить новый)
docker compose exec qa-service uv run python scripts/fill_kb_unified.py --force --url "<URL>"

# Без графа знаний (только чанки + эмбеддинги)
docker compose exec qa-service uv run python scripts/fill_kb_unified.py --no-graph --url "<URL>"
```

---

## PDF документы

**Метод обработки (универсальный):** скачать → pdfplumber (рендер 220 DPI) → pytesseract (rus+eng, --oem 3 --psm 1) → текст → LightRAG

Любой PDF URL можно передать через `--url`. Title извлекается из имени файла (URL-decoded).

### Confluence Help (2 PDF)

| # | Описание | URL |
|---|----------|-----|
| 1 | Условия по использованию услуг Wi-Fi | `https://confluence.utmn.ru/download/attachments/8037875/terms.4be25f01.pdf?version=1&modificationDate=1615881981974&api=v2` |
| 2 | Положение о порядке использования сети Интернет | `https://confluence.utmn.ru/download/attachments/8037875/247_1.pdf?version=1&modificationDate=1621592539032&api=v2` |

### Confluence Study



### Sveden (35 PDF)

#### Устав и изменения (8)

| # | Описание | URL |
|---|----------|-----|
| 1 | Устав ТюмГУ 2018 | `https://www.utmn.ru/upload/medialibrary/de7/%D0%A3%D1%81%D1%82%D0%B0%D0%B2%202018.pdf` |
| 2 | Изменения в Устав (15.04.2020) | `https://www.utmn.ru/upload/medialibrary/bdf/Izmeneniya-v-Ustav-TyumGU-_14.04.2020_.pdf` |
| 3 | Изменения в Устав (26.12.2019) | `https://www.utmn.ru/upload/medialibrary/810/Izmeneniya-v-Ustav-TyumGU-_26.12.2019_.pdf` |
| 4 | Изменения в Устав (21.03.2022) | `https://www.utmn.ru/upload/medialibrary/715/Izmeneni-v-Ustav-ot-21.03.2022.pdf` |
| 5 | Изменения в Устав (20.09.2022) | `https://www.utmn.ru/upload/medialibrary/295/Izmenenie-v-Ustav-2022-_sentyabr_.pdf` |
| 6 | Изменения в Устав (06.02.2023) | `https://www.utmn.ru/upload/medialibrary/78e/Izmeneniya-v-Ustav-fevral-2023.pdf` |
| 7 | Изменения в Устав (31.03.2023) | `https://www.utmn.ru/upload/medialibrary/1f8/Izmeneniya.pdf` |
| 8 | Изменения в Устав (06.10.2025) | `https://www.utmn.ru/upload/ftp/pdf_merged%20%282%29.pdf` |

#### Филиалы (2)

| # | Описание | URL |
|---|----------|-----|
| 9 | Положение о Тобольском пед. институте | `https://sveden.utmn.ru/sveden/files/pologhenie_o_tobolyskom_pedagogicheskom_institute_(filial)_tyumgu_(2016).pdf` |
| 10 | Положение об Ишимском пед. институте | `https://sveden.utmn.ru/sveden/files/pologhenie_o_ishimskom_pedagogicheskom_institute_(filial)_tyumgu_(2016).pdf` |

#### Правила и порядок (13)

| # | Описание | URL |
|---|----------|-----|
| 11 | Правила внутреннего распорядка | `https://sveden.utmn.ru/sveden/files/eit/Pravila_vnutrennego_rasporyadka_obuchayuschixsya_FGAOU_VO_Tyumenskii_gosudarstvennyi_universitet.pdf` |
| 12 | Правила приёма бакалавриат/специалитет 2026-2027 | `https://sveden.utmn.ru/sveden/files/aid/Pravila_priema_bakspec_na_2026-2027_uchebnyi_god_.pdf` |
| 13 | Правила приёма магистратура 2026-2027 | `https://sveden.utmn.ru/sveden/files/vif/Pravila_priema_na_obuchenie_v_FGAOU_VO_Tyumenskii_gosudarstvennyi_universitet_po_programmam_magistratury_na_2026-2027_uchebnyi_god(1).pdf` |
| 14 | Правила приёма СПО | `https://sveden.utmn.ru/sveden/files/aie/Pravila_priema_SPO_26-27_(1)(1).pdf` |
| 15 | Расписания СПО Колледж ИИи КМ | `https://www.utmn.ru/upload/medialibrary/2eb/6q5jyvk9gzuxjnmqnjp5n130rfe99eop/Polozhenie-o-raspisaniyakh-SPO-Kolledzh-IIi-KM-golovnoy-vuz-02.09.2025.pdf` |
| 16 | Расписания ВО ТюмГУ | `https://www.utmn.ru/upload/medialibrary/df2/udnrhr2hk1wo2h97g02x4pg2nuo8qu7e/Polozhenie-o-raspisaniyakh-po-OP-VO-v-TyumGU-02.09.2025.pdf` |
| 17 | Расписания ВО филиалы | `https://sveden.utmn.ru/sveden/files/Pologhenie_o_raspisaniyax_po_obrazovatelynym_programmam_VO_v_filialax_TyumGU.pdf` |
| 18 | Расписания ВО ТюмГУ (РИЦ) | `https://sveden.utmn.ru/sveden/files/ric/Pologhenie_o_raspisaniyax_po_obrazovatelynym_programmam_vysshego_obrazovaniya_v_TyumGU.pdf` |
| 19 | Расписания СПО Колледж (дубль) | `https://sveden.utmn.ru/sveden/files/eib/Polozhenie-o-raspisaniyakh-SPO-Kolledzh-IIi-KM-golovnoy-vuz-02.09.2025.pdf` |
| 20 | Текущий контроль и аттестация | `https://sveden.utmn.ru/sveden/files/vim/Pologhenie_o_tekuschem_kontrole_uspevaemosti_i_promeghutochnoi_attestacii_obuchayuschixsya_TyumGU.pdf` |
| 21 | Перевод СПО | `https://sveden.utmn.ru/sveden/files/Pologhenie_Perevod_SPO.pdf` |
| 22 | Отчисление и восстановление | `https://sveden.utmn.ru/sveden/files/ail/Pologhenie_o_poryadke_otchisleniya,_vosstanovleniya_obuchayuschixsya_TyumGU(1).pdf` |
| 23 | Перевод ВО | `https://sveden.utmn.ru/sveden/files/vim/Poryadok_perevoda_obuchayuschixsya_po_OP_VO.pdf` |

#### Дополнительные программы (4)

| # | Описание | URL |
|---|----------|-----|
| 24 | Оформление отношений с обучающимися | `https://sveden.utmn.ru/sveden/files/rio/Pologhenie_o_poryadke_oformleniya_vozniknoveniya,_priostanovleniya_i_prekrascheniya_otnosheniy_meghdu_Tyumenskiy_gosudarstvennym_universitetom_i_obuchayuschimisya_i_(ili)_roditelyami_(zakonnymi_predstavitelyami)_nesovershennoletnix_obuchayusch(1).pdf` |
| 25 | Регламент доп. образовательной программы | `https://sveden.utmn.ru/sveden/files/aiw/Reglament_otkrytiya_i_realizacii_dopolnitelynoi_obrazovatelynoi_programmy.pdf` |
| 26 | Доп. профессиональные программы | `https://sveden.utmn.ru/sveden/files/ein/Poryadok_realizacii_dopolnitelynyx_professionalynyx_programm.pdf` |
| 27 | Зачёт дисциплин при ДПП | `https://sveden.utmn.ru/sveden/files/aib/Poryadok_zacheta_uchebnyx_disciplin,_kursov,_modulei,_praktiti_pri_osvoenii_obuchayuschimisya_DPP.pdf` |

#### Аттестация (1)

| # | Описание | URL |
|---|----------|-----|
| 28 | Итоговая аттестация | `https://sveden.utmn.ru/sveden/files/vix/Pologhenie_ob_itogovoi_attestacii.pdf` |

#### Стипендии и меры поддержки (6)

| # | Описание | URL |
|---|----------|-----|
| 29 | Размеры стипендий | `https://sveden.utmn.ru/sveden/files/vie/Prikaz_ot_27.02.2026_No_212-1.pdf` |
| 30 | Стипендиальное обеспечение | `https://sveden.utmn.ru/sveden/files/eiz/Pologhenie_o_stipendialynom_obespechenii_FGAOU_VO_Tyumenskii_gosudarstvennyi_universitet_19.06.2023.pdf` |
| 31 | Поддержка детей-сирот | `https://sveden.utmn.ru/sveden/files/ziv/Pologhenie_o_merax_socialynoi_podderghki_detei-sirot_FGAOU_VO_TyumGU.pdf` |
| 32 | Материальная поддержка | `https://sveden.utmn.ru/sveden/files/riz/Pologhenie_o_poryadke_predostavleniya_materialynoi_podderghki_obuchayuschimsya_TyumGU(1).pdf` |
| 33 | Размеры мат. поддержки СПО и ВО | `https://sveden.utmn.ru/sveden/files/rim/Prikaz_ob_ustanovlenii_razmerov_materialynoi_podderghki_obuchayuschimsya_po_obrazovatelynym_programmam_SPO_i_VO_.pdf` |
| 34 | Плата за проживание | `https://sveden.utmn.ru/sveden/files/eio/Prikaz_ot_09.02.2026_No_121-1_Ob_ustanovlenii_razmerov_platy_za_proghivanie_obuchayusch,_Tyumeny.pdf` |

#### Платные услуги (1)

| # | Описание | URL |
|---|----------|-----|
| 35 | Платные образовательные услуги | `https://sveden.utmn.ru/sveden/files/zin/606_1.pdf` |

### UTMN (динамические)

PDF документы обнаруживаются автоматически на 23 страницах `utmn.ru` при массовом запуске. Для инкрементального добавления конкретного PDF с `utmn.ru` — передайте его URL через `--url`.

---

## HTML страницы

### Confluence Help (6 страниц)

**Метод обработки:** Confluence REST API (`/rest/api/content/{id}?expand=body.export_view`) → JSON → `body.export_view.value` (HTML) → BeautifulSoup `get_text(separator=" ")` → plain text → LightRAG

Для страниц с `children: true` — рекурсивный обход дочерних через `/child/page?limit=100` (при массовом запуске; при `--url` индексируется только сама страница).

| # | Страница | URL | Дочерние |
|---|----------|-----|----------|
| 1 | Карты доступа | `https://confluence.utmn.ru/pages/viewpage.action?pageId=8037241` | Нет |
| 2 | Корпоративная учётная запись | `https://confluence.utmn.ru/pages/viewpage.action?pageId=8037222` | Нет |
| 3 | Яндекс 360 | `https://confluence.utmn.ru/pages/viewpage.action?pageId=62586931` | Да |
| 4 | Единый личный кабинет ТюмГУ | `https://confluence.utmn.ru/pages/viewpage.action?pageId=121923452` | Да |
| 5 | Основы работы с LMS | `https://confluence.utmn.ru/pages/viewpage.action?pageId=121906735` | Нет |
| 6 | Беспроводная сеть Wi-Fi | `https://confluence.utmn.ru/pages/viewpage.action?pageId=8037245` | Нет |

### Sveden (3 страницы)

**Метод обработки:** HTTP GET → HTML → BeautifulSoup → поиск контент-области (`div.main-content` / `div.content` / `main`) → разбиение на секции по заголовкам (`h2`/`h3`/`h4`) → для каждой секции: `_html_table_to_text()` — заголовки столбцов из `<thead>` / `<th>`, каждая строка: `Заголовок1: значение1; Заголовок2: значение2` (столбец "№" пропускается) → LightRAG

| # | Страница | URL |
|---|----------|-----|
| 1 | Руководство ТюмГУ | `https://sveden.utmn.ru/sveden/managers/` |
| 2 | Организация питания | `https://sveden.utmn.ru/sveden/catering/` |
| 3 | Структура и органы управления | `https://sveden.utmn.ru/sveden/struct` |

---

## Маршрутизация URL

При передаче `--url` скрипт автоматически определяет тип обработки:

| URL-паттерн | source_type | Метод |
|-------------|-------------|-------|
| `confluence.utmn.ru` + `pageId=` | `confluence_help` | REST API → HTML |
| `confluence.utmn.ru` + `.pdf` | `confluence_help` | OCR |
| `sveden.utmn.ru/sveden/managers/` | `sveden` | HTML + таблицы |
| `sveden.utmn.ru/sveden/catering/` | `sveden` | HTML + таблицы |
| `sveden.utmn.ru/sveden/struct` | `sveden` | HTML + таблицы |
| `sveden.utmn.ru` + `.pdf` | `sveden` | OCR |
| `utmn.ru` + `.pdf` | `utmn` | OCR |
| Любой `.pdf` | `utmn` | OCR (fallback) |
