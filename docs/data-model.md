# Модель данных

Источник истины — `SCHEMA` в `portal/db.py` (строки 12–99). БД — один файл
SQLite (`aiosqlite`), без внешнего сервера и без версионированных
миграционных файлов: единственная миграция —
`migrate_prompt_templates` (`portal/db.py:249`), которая на каждом старте
дописывает недостающие плейсхолдеры в уже сохранённые prompt-шаблоны
пользователя, чтобы старые кастомизации не ломались при обновлении кода.

Общие соглашения:

- `activity_id` — не автоинкремент и не UUID, а составной ключ
  `f"{sid}:{key}:{time}"`, собранный из полей ответа Xiaomi
  (`mi_fitness_sync/activity/models.py:44`).
- Поля с суффиксом `_json` физически хранятся как `TEXT` и
  (де)сериализуются вручную через `json.dumps`/`json.loads`
  (`_serialize_json` / `_deserialize_json_field` в `portal/db.py` и
  `portal/sync.py`).
- Даты — ISO 8601 UTC-строки (`utc_now_iso()`), не SQLite `DATETIME`.
- Внешние ключи объявлены в схеме (`FOREIGN KEY`), но `PRAGMA
  foreign_keys = ON` включается только при обычном подключении
  (`connect_db`), не при `init_db` — при первом создании схемы
  проверка ссылочной целостности не активна.

## `activities`

Одна строка — одна пробежка. Наполняется из `_serialize_activity`
(`portal/sync.py:62`), которая вытаскивает поля из `raw_report` (сырого
JSON-отчёта Xiaomi) под несколькими альтернативными именами ключей
(`pick_int("avg_hrm", "avg_heart_rate", "heart_rate_avg")`) — формат ответа
Xiaomi не задокументирован и, судя по коду, не полностью стабилен между
устройствами.

| Поле | Тип | Описание |
| --- | --- | --- |
| `activity_id` | TEXT PK | `sid:key:time`, см. выше |
| `date` | TEXT | ISO-время старта (UTC) |
| `distance_km` | REAL | |
| `duration_seconds` | INTEGER | |
| `avg_hrm` | INTEGER | средний пульс |
| `avg_pace` | INTEGER | средний темп, секунд на км |
| `avg_cadence` | INTEGER | средний каденс |
| `avg_stride` | INTEGER | средняя длина шага |
| `train_load` | INTEGER | тренировочная нагрузка (Training Load) |
| `recover_time` | INTEGER | рекомендованное время восстановления, часы |
| `vo2_max` | INTEGER | |
| `aerobic_train_effect` / `anaerobic_train_effect` | REAL | |
| `hrm_warm_up_duration` … `hrm_extreme_duration` | INTEGER | длительности по пульсовым зонам (5 колонок) |
| `avg_vertical_stride_ratio` | REAL | |
| `avg_touchdown_duration` | INTEGER | |
| `avg_vertical_amplitude` | REAL | |
| `raw_report` | TEXT (JSON) | необработанный отчёт Xiaomi — источник для всех полей выше и для запасного парсинга |
| `synced_at` | TEXT | момент записи в БД портала |

При повторной синхронизации строка перезаписывается целиком
(`INSERT OR REPLACE`, `portal/db.py:340`) — истории изменений одной
активности нет, только последний известный снимок.

Импортируются только активности с `category == "running"` и
`distance_meters > 300` (`portal/sync.py:303`) — остальные типы
тренировок Mi Fitness (плавание, велосипед и т.д.) в БД не попадают
вообще.

## `activity_details`

Детали одной пробежки — GPS-трек и посекундные показатели. Заполняется
лениво (по клику или автоматически для единственной новой активности за
синхронизацию), кэш живёт `DETAIL_CACHE_TTL_DAYS = 7` дней
(`portal/sync.py:33`, проверка в `fetch_detail`).

| Поле | Тип | Описание |
| --- | --- | --- |
| `activity_id` | TEXT PK, FK → `activities.activity_id` | |
| `samples` | TEXT (JSON) | список посекундных сэмплов: пульс, каденс, скорость, дистанция, высота, шаги, калории — см. `ActivitySample.to_json_dict` |
| `track_points` | TEXT (JSON) | список GPS-точек: широта/долгота, высота, скорость, дистанция, пульс, каденс — см. `TrackPoint.to_json_dict` |
| `raw_detail` | TEXT (JSON) | необработанный ответ Xiaomi (JSON-детали и/или сведения о скачанных FDS-файлах) |
| `fetched_at` | TEXT | момент загрузки — точка отсчёта для TTL |

## `sync_log`

История запусков синхронизации.

| Поле | Тип | Описание |
| --- | --- | --- |
| `id` | INTEGER PK AUTOINCREMENT | |
| `started_at` / `finished_at` | TEXT | |
| `activities_added` / `activities_updated` | INTEGER | |
| `error` | TEXT | текст ошибки, если синхронизация упала |

`GET /api/sync/status` отдаёт последние 10 записей.

## `ai_analysis`

Кэш текстового разбора одной пробежки от AI-тренера.

| Поле | Тип | Описание |
| --- | --- | --- |
| `activity_id` | TEXT PK, FK → `activities.activity_id` | |
| `analysis` | TEXT | готовый текст ответа Claude |
| `created_at` | TEXT | |

Одна запись на активность (`INSERT OR REPLACE`) — предыдущий разбор
теряется при пересчёте (`force_refresh`).

## `daily_recommendation`

История «ответа на сегодня» — в отличие от `ai_analysis`, это лог
(`INSERT`, не `REPLACE`): каждая генерация добавляет новую строку, на
дашборде показывается последняя по `id`.

| Поле | Тип | Описание |
| --- | --- | --- |
| `id` | INTEGER PK AUTOINCREMENT | |
| `date` | TEXT | дата генерации (`YYYY-MM-DD`, из `generated_at`) |
| `status` | TEXT | `run` \| `run_easy` \| `rest` |
| `message` | TEXT | текст рекомендации от AI |
| `generated_at` | TEXT | |
| `sync_id` | INTEGER FK → `sync_log.id`, nullable | синхронизация, после которой сгенерирована (`NULL` при ручном обновлении через `/api/ai/recommendation/refresh`) |

## `settings`

Плоское key-value хранилище с 10 сидируемыми ключами
(`DEFAULT_SETTINGS`, `portal/db.py:101`), из них 8 редактируются через
`GET/POST /api/settings` (`EDITABLE_SETTING_KEYS`,
`portal/routers/settings.py:14`):

| Поле | Тип |
| --- | --- |
| `key` | TEXT PK |
| `value` | TEXT |
| `updated_at` | TEXT |

Ключи: `daily_prompt_template`, `activity_prompt_template`,
`target_hr_zone_low`, `target_hr_zone_high`, шесть `dashboard_card_*`
(вкл/выкл карточек дашборда). Есть и нередактируемый через UI служебный
ключ `daily_recommendation_error` (`portal/routers/ai.py:34`) — хранит
последнюю ошибку генерации рекомендации в виде JSON, чтобы дашборд мог
показать её вместо устаревшей рекомендации.

**Важно:** промпт для третьей AI-функции (предложение цели на месяц)
в `settings` не хранится — он захардкожен строкой прямо в
`generate_goal_suggestion` (`portal/routers/ai.py:515`) и через UI не
редактируется, в отличие от двух остальных.

## `monthly_goals`

| Поле | Тип | Описание |
| --- | --- | --- |
| `id` | INTEGER PK AUTOINCREMENT | |
| `year` / `month` | INTEGER | уникальная пара (`UNIQUE(year, month)`) |
| `km_goal` | REAL | |
| `runs_goal` | INTEGER | |
| `created_at` | TEXT | |
| `ai_suggestion` | TEXT, nullable | текст обоснования от AI (или от эвристического fallback), сохранённый на момент установки цели |

## `health_states`

Журнал состояния — записи о самочувствии, боли, травмах с периодом
действия.

| Поле | Тип | Описание |
| --- | --- | --- |
| `id` | INTEGER PK AUTOINCREMENT | |
| `description` | TEXT | свободный текст, до 5000 символов (валидация в `portal/routers/health.py`) |
| `started_at` | TEXT | |
| `ended_at` | TEXT, nullable | `NULL` = состояние ещё активно |
| `created_at` / `updated_at` | TEXT | |

Последние 3 записи (`ORDER BY started_at DESC, id DESC`) подмешиваются
во все три AI-промпта через `format_health_lines`
(`portal/routers/ai.py:260`).
