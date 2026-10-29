# Devir sırasındaki salt okunur kanıt — 29 Ekim 2026

Bu kayıt canlı hesap ekranı gözlemi değildir. SQL status API iddiasıdır; prepared paylaşılmış sayılmaz. Tarihli sağlık her gelecekteki tur için garanti değildir.

```json
{
  "captured_at": "2026-10-29T06:42:56.865679+00:00",
  "main_sha": "9296acfae3f797294fd1a6ea3b7611fe377db2c7",
  "state_sha": "89e6e3486f093352bdb0f4b570abaf590b847c35",
  "pages_generated_at": "2026-10-29T09:00:50.394600+03:00",
  "frozen_comparison": {
    "posts": {
      "old_rows": 54,
      "all_sql_columns_unchanged": true
    },
    "facebook_deliveries": {
      "old_rows": 52,
      "all_sql_columns_unchanged": true
    },
    "weather_stories": {
      "old_rows": 10,
      "all_sql_columns_unchanged": true
    },
    "pharmacy_stories": {
      "old_rows": 3,
      "all_sql_columns_unchanged": true
    }
  },
  "recent_frozen_comparison": {
    "posts": {
      "rows": 58,
      "all_sql_columns_unchanged": true
    },
    "facebook_deliveries": {
      "rows": 56,
      "all_sql_columns_unchanged": true
    },
    "weather_stories": {
      "rows": 11,
      "all_sql_columns_unchanged": true
    },
    "pharmacy_stories": {
      "rows": 4,
      "all_sql_columns_unchanged": true
    }
  },
  "frozen_images": {
    "illustrations": {
      "referenced_rows": 11,
      "all_retained_columns_and_bytes_unchanged": true,
      "all_existing_pixel_bytes_unchanged": true,
      "previously_pruned_empty_failure_rows": [],
      "historical_cache_differences": []
    },
    "source_photos": {
      "referenced_rows": 1,
      "all_retained_columns_and_bytes_unchanged": true,
      "all_existing_pixel_bytes_unchanged": true,
      "previously_pruned_empty_failure_rows": [],
      "historical_cache_differences": []
    }
  },
  "ready_covers": 3,
  "waiting_covers": 3,
  "historical_live_assets_exact_bytes": 8,
  "platform_ui_observed": false
}
```

## 29 Ekim 2026 akşam — Claude Code salt okunur doğrulaması

Kaynak: `automation-state` dalındaki `platform.sqlite` bütün sütun karşılaştırması, Pages `data.json` ve JPEG hash'leri, GitHub Actions iş sonuçları. Platform ekranı gözlenmedi. Seferihisar'da kod, yapılandırma veya durum değiştirilmedi.

```json
{
  "main_sha": "9296acfae3f797294fd1a6ea3b7611fe377db2c7",
  "state_sha": "5776fcacaf770cafcea1f64425d3465a7a55448c",
  "pages_generated_at": "2026-10-29T23:19:30.868716+03:00",
  "frozen_sql_all_columns_unchanged": {
    "baseline_26_oct": {"posts": 54, "facebook_deliveries": 52, "weather_stories": 10, "pharmacy_stories": 3},
    "closure_28_oct": {"posts": 58, "facebook_deliveries": 56, "weather_stories": 11, "pharmacy_stories": 4},
    "handoff_29_oct_0642_utc": {"posts": 60, "facebook_deliveries": 58, "weather_stories": 12, "pharmacy_stories": 4}
  },
  "frozen_images_byte_identical": {"illustrations": 11, "source_photos": 1},
  "pages_frozen_editions_unchanged": 16,
  "historical_restored_assets_rehashed_exact": 8,
  "today_api_claims": {
    "news_pairs": ["08:31", "12:46", "15:15"],
    "facebook_feed_story_pairs": 3,
    "weather_story": "08:00",
    "pharmacy_story": "17:00",
    "daily_limit_check": "19:00",
    "evening_fourth": "awaiting_content_visual"
  },
  "prepared_news": {"verified_cover": 12, "awaiting_visual": 3},
  "source_health_failed": ["instagram-gundem", "seferihisar-mem", "bubilet", "bubilet-bademler"],
  "platform_ui_observed": false
}
```

### 27–28 Ekim üretim kesintisi

27 Ekim 11:47 UTC – 28 Ekim 22:41 UTC arasında `Research and prepare` 78 çalışmanın 67'sinde "Validate both public boundaries before upload" adımında başarısız oldu (ilk ve son örnek: 40498810950, 40781873837). Persist adımı atlandığı için durum bozulmadı. Sonuçlar: 27 Ekim akşamı – 28 Ekim gecesi haber paylaşılmadı; 28 Ekim hava story'si yok (zamanlanmış hava işleri 10:47/10:57 UTC'de, pencere dışında tetiklendi); 27 ve 28 Ekim eczane story'leri yok. PR #80 (28 Ekim 22:56 UTC) sonrası toparlandı. 29 Ekim'de 39 research çalışmasından biri (13:17 UTC, durum geri yükleme adımı) başarısız oldu; nedeni log erişimi olmadan doğrulanmadı.

### Yayın tetiklemesi iptalleri

Research bittiğinde `publish.yml`, `weather-story.yml` ve `pharmacy-story.yml` aynı anda `workflow_run` ile tetiklenir ve aynı `seferihisar-production` kilidini paylaşır. GitHub bu grupta tek bekleyen çalışmaya izin verdiği için yayın çalışması iş başlamadan `cancelled` olabilir: 29 Ekim'de 39 yayın çalışmasının 15'i, 22 Ekim'de 48'in 10'u. Yayın kaybı gözlenmedi; bir sonraki research turu (15–30 dk) yeniden dener. Isparta'da yayın, research iş akışının içinde ayrı iştir. Değişiklik yapılmadı.

### Görsel önbelleği

80/80 hazır görsel, 7,8 MiB / 12 MiB: 17 donmuş (yayına bağlı, 1,4 MiB), 12 etkin taslak, 51 budanabilir eski taslak. Donmuş görseller günde yaklaşık 1–3 artıyor; kabaca 3–9 hafta içinde yeni taslaklar için yer daralabilir. 12–17 Ekim'de yayımlanmış 5 gönderinin kaynak görseli 26 Ekim korumasından önce kaybolmuştur (onarım manifestinde yok; Meta teslimi etkilenmez). Uzun vadeli saklama stratejisi ayrıca kararlaştırılmalıdır.
