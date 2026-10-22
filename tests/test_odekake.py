import os
from pathlib import Path as _P

# 福井のデータで書いたテストなので、どの県のリポジトリでも福井の設定で走らせる
os.environ["REGION_FILE"] = str(_P(__file__).resolve().parent / "region_fukui.json")
import importlib.util
import re
import unittest
from datetime import date
from pathlib import Path

_path = Path(__file__).resolve().parent.parent / "scripts" / "おでかけ.py"
_spec = importlib.util.spec_from_file_location("odekake", _path)
odekake = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(odekake)

BASE = date(2026, 9, 30)

NETA = """# ネタ帳

## 書き足す場所

### 2026-09-30

- 10/3-4 坂井市ゆりの里公園で「さかい米フェス2026」開催（→ 新米の2日間）
- 福井市に「テスト店」が2026年6月13日オープン（→ 新しい店）

<details><summary>出典</summary>

- https://example.com/a
- https://example.com/b

</details>

### 2026-09-29

- 10/3-4 坂井市ゆりの里公園で「さかい米フェス2026」開催（→ 古いほう）
- 日付のない話題（→ ひとこと）

## 書き方のヒント

- ここは読まない
"""


class ParseDatesTest(unittest.TestCase):
    def test_range_in_same_month(self):
        self.assertEqual(odekake.parse_dates("10/3-4 開催", BASE), (date(2026, 10, 3), date(2026, 10, 4)))

    def test_range_across_months(self):
        self.assertEqual(odekake.parse_dates("9/26-10/12 展示", BASE), (date(2026, 9, 26), date(2026, 10, 12)))

    def test_range_with_weekday_and_wave_dash(self):
        self.assertEqual(odekake.parse_dates("開催中（9/10〜11/3）", BASE), (date(2026, 9, 10), date(2026, 11, 3)))

    def test_listed_dates_become_span(self):
        self.assertEqual(odekake.parse_dates("9/25・10/2・10/30に実施", BASE), (date(2026, 9, 25), date(2026, 10, 30)))

    def test_fullwidth_weekday_range(self):
        # ぎふあいちの収集は全角のかっこで書く（2026-10-15 運用部・ぎふあいち担当）
        self.assertEqual(odekake.parse_dates("10/10（土）〜18（日）展示", BASE), (date(2026, 10, 10), date(2026, 10, 18)))

    def test_same_month_days_with_dot(self):
        self.assertEqual(odekake.parse_dates("10/17・18 クラフトフェア", BASE), (date(2026, 10, 17), date(2026, 10, 18)))
        self.assertEqual(odekake.parse_dates("10/24（土）・25（日）祭り", BASE), (date(2026, 10, 24), date(2026, 10, 25)))

    def test_until_starts_from_written_day(self):
        self.assertEqual(odekake.parse_dates("11/29までの金・土・日に開催", BASE), (BASE, date(2026, 11, 29)))
        self.assertEqual(odekake.parse_dates("12月6日まで展示", BASE), (BASE, date(2026, 12, 6)))
        # 書いた日より前の「まで」は今まで通り
        self.assertEqual(odekake.parse_dates("9/20まで募集", BASE), (date(2026, 9, 20), date(2026, 9, 20)))

    def test_single_with_weekday_and_time(self):
        self.assertEqual(odekake.parse_dates("10/25(日)10時〜15時30分 そばまつり", BASE), (date(2026, 10, 25), date(2026, 10, 25)))

    def test_japanese_date_with_year(self):
        self.assertEqual(odekake.parse_dates("2026年5月1日オープン", BASE), (date(2026, 5, 1), date(2026, 5, 1)))

    def test_january_written_in_autumn_is_next_year(self):
        self.assertEqual(odekake.parse_dates("1/10 開催", BASE)[0], date(2027, 1, 10))

    def test_no_date(self):
        self.assertEqual(odekake.parse_dates("参加者募集中", BASE), (None, None))


class GuessTest(unittest.TestCase):
    def test_area_uses_earliest_place(self):
        self.assertEqual(odekake.guess_area("あわら市温泉の店。三国産海鮮を使う"), "あわら市")

    def test_area_prefers_longer_name(self):
        self.assertEqual(odekake.guess_area("南越前町で開催"), "南越前町")

    def test_kind(self):
        self.assertEqual(odekake.guess_kind("福井市に店がオープン"), "スポット")
        self.assertEqual(odekake.guess_kind("10/3 まつり開催"), "催し")


class BuildTest(unittest.TestCase):
    def test_build(self):
        data = odekake.build(NETA)
        self.assertEqual(data["updated"], "2026-09-30")
        texts = [it["text"] for it in data["items"]]
        self.assertEqual(len(texts), 3)  # 重複は新しいほうだけ、ヒント欄は読まない
        fes = data["items"][0]
        self.assertEqual(fes["note"], "新米の2日間")
        self.assertEqual(fes["source"], "https://example.com/a")
        self.assertEqual((fes["area"], fes["region"], fes["kind"]), ("坂井市", "嶺北", "催し"))
        shop = data["items"][1]
        self.assertEqual((shop["kind"], shop["start"]), ("スポット", "2026-06-13"))

    def test_pick_from_daihyo_section(self):
        md = NETA.replace("### 2026-09-30\n", "### 2026-09-30（代表が見つけた催し）\n", 1)
        items = odekake.build(md)["items"]
        self.assertTrue(all(it["pick"] for it in items if it["written"] == "2026-09-30"))
        self.assertFalse(any(it["pick"] for it in items if it["written"] == "2026-09-29"))

    def test_sources_not_paired_when_counts_differ(self):
        data = odekake.build(NETA)
        topic = [it for it in data["items"] if it["text"].startswith("日付のない")][0]
        self.assertIsNone(topic["source"])
        self.assertIsNone(topic["start"])


class InstagramTest(unittest.TestCase):
    def test_split_instagram_post_after_note(self):
        line = "10/3 祭り開催（→ ひとこと） ［Instagram: https://www.instagram.com/p/AbC-12_x/?igsh=xyz］"
        rest, url = odekake.split_instagram(line)
        self.assertEqual(rest, "10/3 祭り開催（→ ひとこと）")
        self.assertEqual(url, "https://www.instagram.com/p/AbC-12_x/")
        self.assertEqual(odekake.split_note(rest), ("10/3 祭り開催", "ひとこと"))

    def test_split_instagram_normalizes_reels(self):
        _, url = odekake.split_instagram("催し ［Instagram: https://www.instagram.com/reels/Dd3Y2lFNBiZ/］")
        self.assertEqual(url, "https://www.instagram.com/reel/Dd3Y2lFNBiZ/")

    def test_split_instagram_none(self):
        self.assertEqual(odekake.split_instagram("ふつうの行"), ("ふつうの行", None))

    def test_build_keeps_instagram(self):
        md = NETA.replace("（→ 新しい店）", "（→ 新しい店） ［Instagram: https://www.instagram.com/test_shop/］")
        shop = [it for it in odekake.build(md)["items"] if "テスト店" in it["text"]][0]
        self.assertEqual(shop["instagram"], "https://www.instagram.com/test_shop/")
        self.assertEqual(shop["note"], "新しい店")


class ThumbTest(unittest.TestCase):
    def test_find_og_image_relative_and_attribute_order(self):
        html = '<head><meta content="/img/a.jpg" property="og:image"><meta name="twitter:image" content="https://x/b.jpg"></head>'
        self.assertEqual(odekake.find_og_image(html, "https://fupo.jp/event/x/"), "https://fupo.jp/img/a.jpg")

    def test_find_og_image_falls_back_to_twitter(self):
        html = "<meta name='twitter:image' content='https://ex.com/t.png?a=1&amp;b=2'>"
        self.assertEqual(odekake.find_og_image(html, "https://ex.com/"), "https://ex.com/t.png?a=1&b=2")

    def test_find_og_image_skips_site_logo(self):
        html = '<meta property="og:image" content="https://www.city.sabae.fukui.jp/images/ogp.png">'
        self.assertIsNone(odekake.find_og_image(html, "https://www.city.sabae.fukui.jp/"))
        html = '<meta property="og:image" content="https://ex.jp/wp-content/uploads/2024/06/cropped-header.png">'
        self.assertIsNone(odekake.find_og_image(html, "https://ex.jp/"))

    def test_find_og_image_keeps_uploaded_ogp(self):
        url = "https://renew-fukui.com/kanri/wp-content/uploads/2026/06/SNS-OGP_1200x675px.jpg"
        html = f'<meta property="og:image" content="{url}">'
        self.assertEqual(odekake.find_og_image(html, "https://renew-fukui.com/"), url)

    def test_attach_og_remembers_404_but_retries_5xx(self):
        import urllib.error

        def fake(url):
            raise urllib.error.HTTPError(url, 404 if "gone" in url else 503, "x", {}, None)

        items = [{"source": "https://ex.com/gone"}, {"source": "https://ex.com/busy"}]
        prev = {}
        odekake.attach_og(items, prev, fetch=fake)
        self.assertEqual(prev, {"https://ex.com/gone": None})
        self.assertNotIn("og", items[1])

    def test_find_og_image_none(self):
        self.assertIsNone(odekake.find_og_image("<title>x</title>", "https://ex.com/"))

    def test_parse_og_collects_card_fields(self):
        html = (
            '<head><title>ページ | サイト</title>'
            '<meta property="og:title" content="さかい米フェス2026">'
            '<meta property="og:description" content="  新米の食べ比べ\n と 交流  ">'
            '<meta property="og:site_name" content="ふーぽ">'
            '<meta property="og:image" content="/img/fes.jpg"></head>'
        )
        og = odekake.parse_og(html, "https://fupo.jp/event/x/")
        self.assertEqual(og, {
            "image": "https://fupo.jp/img/fes.jpg",
            "title": "さかい米フェス2026",
            "description": "新米の食べ比べ と 交流",
            "site": "ふーぽ",
        })

    def test_parse_og_falls_back_to_title_and_description(self):
        html = '<title>坂井市｜お知らせ</title><meta name="description" content="' + "あ" * 200 + '">'
        og = odekake.parse_og(html, "https://ex.jp/")
        self.assertEqual(og["title"], "坂井市｜お知らせ")
        self.assertIsNone(og["image"])
        self.assertEqual(len(og["description"]), odekake.OG_DESC_MAX)
        self.assertTrue(og["description"].endswith("…"))

    def test_parse_og_none_when_empty(self):
        self.assertIsNone(odekake.parse_og("<p>x</p>", "https://ex.jp/"))

    def test_attach_og_uses_cache_and_skips_instagram_and_retries_errors(self):
        items = [
            {"source": "https://a.example/1"},
            {"source": "https://b.example/2"},
            {"source": "https://www.instagram.com/shop/"},
            {"source": "https://c.example/3"},
            {"source": None},
        ]
        calls = []

        def fake(url):
            calls.append(url)
            if "c.example" in url:
                raise OSError("timeout")
            return '<meta property="og:title" content="B"><meta property="og:image" content="https://img.example/b.jpg">'

        cached = {"image": None, "title": "A", "description": None, "site": None}
        prev = {"https://a.example/1": cached}
        n = odekake.attach_og(items, prev, fetch=fake)
        self.assertEqual(calls, ["https://b.example/2", "https://c.example/3"])
        self.assertEqual(n, 1)
        self.assertEqual(items[0]["og"], cached)
        self.assertEqual(items[1]["og"]["title"], "B")
        self.assertEqual(items[1]["og"]["image"], "https://img.example/b.jpg")
        self.assertIsNone(items[2]["og"])
        self.assertNotIn("og", items[3])  # 失敗は覚えない
        self.assertNotIn("https://c.example/3", prev)


class PrerenderTest(unittest.TestCase):
    def test_prerender_lists_only_alive_events_and_escapes(self):
        data = {"items": [
            {"text": "10/10 坂井市で「祭り<1>」開催", "note": "ひとこと", "kind": "催し", "area": "坂井市",
             "start": "2026-10-10", "end": "2026-10-10", "source": "https://ex.jp/a?x=1&y=2"},
            {"text": "9/1 終わった「古い催し」", "note": "", "kind": "催し", "area": None,
             "start": "2026-09-01", "end": "2026-09-01", "source": None},
            {"text": "福井市に「新店」がオープン", "note": "", "kind": "スポット", "area": "福井市",
             "start": "2026-09-20", "end": "2026-09-20", "source": None},
        ]}
        html = odekake.prerender(data, date(2026, 10, 4))
        self.assertTrue(html.startswith(odekake.MARK_START) and html.endswith(odekake.MARK_END))
        self.assertIn("祭り&lt;1&gt;", html)
        self.assertIn("10月10日（土）", html)
        self.assertIn("x=1&amp;y=2", html)
        self.assertNotIn("古い催し", html)
        self.assertIn("2026年9月20日オープン", html)


class MonthPageTest(unittest.TestCase):
    def _ev(self, start, end, area="福井市", text="「テスト祭」開催"):
        return {"kind": "催し", "start": start, "end": end, "area": area, "text": text, "note": "", "source": None}

    def test_only_current_and_later_months_with_enough_short_events(self):
        items = [self._ev(f"2026-10-{d:02d}", f"2026-10-{d:02d}") for d in range(1, 6)]
        items += [self._ev("2026-11-01", "2026-11-01")] * 3
        items += [self._ev("2026-09-01", "2026-09-01")] * 6
        items.append(self._ev("2026-09-01", "2026-12-31"))  # 長いものは件数に数えない
        pages = odekake.month_pages({"items": items}, date(2026, 10, 4))
        self.assertEqual(list(pages), ["2026-10"])
        self.assertEqual(len(pages["2026-10"]["short"]), 5)
        self.assertEqual(len(pages["2026-10"]["long"]), 1)

    def test_keeps_past_months_already_made(self):
        items = [self._ev(f"2026-09-{d:02d}", f"2026-09-{d:02d}") for d in range(1, 6)]
        items += [self._ev(f"2026-10-{d:02d}", f"2026-10-{d:02d}") for d in range(1, 6)]
        pages = odekake.month_pages({"items": items}, date(2026, 11, 2), keep={"2026-09", "2026-10"})
        self.assertEqual(list(pages), ["2026-09", "2026-10"])

    def test_render_month_escapes_and_marks_ended(self):
        b = {"short": [self._ev("2026-10-01", "2026-10-01", text="「<b>祭</b>」開催")], "long": []}
        html = odekake.render_month("2026-10", b, ["2026-10"], date(2026, 10, 4))
        self.assertIn("福井のイベント 2026年10月", html)
        self.assertIn("&lt;b&gt;祭&lt;/b&gt;", html)
        self.assertIn("<small>終了</small>", html)
        self.assertIn('<link rel="canonical" href="https://odekake.fukui-fukui.com/month/2026-10/">', html)

    def test_title_drops_leading_date(self):
        self.assertEqual(odekake._title({"text": "10/3-4 越前陶芸村で陶芸祭。前回は1万人"}), "越前陶芸村で陶芸祭")


if __name__ == "__main__":
    unittest.main()


class InlineSourceTest(unittest.TestCase):
    def test_inline_source_is_taken_out_of_text(self):
        line = "10/25 福井市で「テスト祭」 ［出典: 福井テレビ（Yahoo!ニュース） https://news.yahoo.co.jp/articles/abc と、代表が送った画面］"
        text, url = odekake.split_inline_source(line)
        self.assertEqual(text, "10/25 福井市で「テスト祭」")
        self.assertEqual(url, "https://news.yahoo.co.jp/articles/abc")

    def test_no_inline_source(self):
        self.assertEqual(odekake.split_inline_source("「テスト祭」"), ("「テスト祭」", None))


class DiscreteDaysTest(unittest.TestCase):
    def test_jp_same_month_days(self):
        self.assertEqual(odekake.parse_dates("11月7日・8日に開催", date(2026, 10, 10)),
                         (date(2026, 11, 7), date(2026, 11, 8)))

    def test_discrete_days_are_kept(self):
        items = odekake.parse_neta("## 書き足す場所\n\n### 2026-10-10\n\n- 10/17・24・31 に福井市で「テスト市」開催\n")
        self.assertEqual(items[0]["days"], ["2026-10-17", "2026-10-24", "2026-10-31"])
        self.assertEqual(odekake._when(items[0]), "10月17日（土）・24日（土）・31日（土）")

    def test_consecutive_days_have_no_days_field(self):
        items = odekake.parse_neta("## 書き足す場所\n\n### 2026-10-10\n\n- 10/17・18 に福井市で「テスト市」開催\n")
        self.assertNotIn("days", items[0])

    def test_discrete_with_to_and_months(self):
        self.assertEqual(odekake.discrete_days("10/18(日)と10/25(日)に開催", date(2026, 10, 10)),
                         [date(2026, 10, 18), date(2026, 10, 25)])
        self.assertEqual(odekake.discrete_days("10/4 開催。次回は12/5", date(2026, 10, 10)), [])

    def test_jp_range_is_not_discrete(self):
        items = odekake.parse_neta("## 書き足す場所\n\n### 2026-10-10\n\n- 9月15日〜12月15日に中能登町で「テスト」開催\n")
        self.assertNotIn("days", items[0])


class TitleTest(unittest.TestCase):
    def test_picks_the_subject_not_the_place(self):
        t = odekake._title({"text": "9/8 美浜町の道の駅「若狭美浜はまびより」内にカラオケバー「美ton（ビトン）」が新オープン"})
        self.assertEqual(t, "美ton（ビトン）")

    def test_quote_in_later_sentence_is_not_used(self):
        t = odekake._title({"text": "10/16-25 小浜市で個展「suwayuumi solo exhibition」。箸づくりで出る「おがくず」を使う"})
        self.assertEqual(t, "suwayuumi solo exhibition")

    def test_period_inside_quote(self):
        self.assertEqual(odekake._title({"text": "金沢に朝ごはん専門店「けれんしあ。」がオープン"}), "けれんしあ。")


class EventLdTest(unittest.TestCase):
    def test_month_page_has_event_list_and_anchors(self):
        import json as _json
        ev = {"kind": "催し", "start": "2026-10-24", "end": "2026-10-24", "area": "福井市",
              "text": "10/24 福井市で「テスト祭」開催", "note": "", "source": "https://example.com/a"}
        html = odekake.render_month("2026-10", {"short": [ev], "long": []}, ["2026-10"], date(2026, 10, 4))
        ld = _json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.S).group(1))
        item = ld["@graph"][1]["itemListElement"][0]["item"]
        self.assertEqual((item["@type"], item["name"], item["startDate"]), ("Event", "テスト祭", "2026-10-24"))
        self.assertEqual(item["location"]["address"]["addressRegion"], "福井県")
        self.assertIn(f'<article id="{odekake._anchor(ev)}"', html)


class MergeSameEventTest(unittest.TestCase):
    def test_same_name_and_date_is_kept_once_and_undated_is_dropped(self):
        md = ("## 書き足す場所\n\n### 2026-10-15\n\n- 10/24 金沢市で「台南美食フェア」開催。屋台が並ぶ\n"
              "- 11/14・15 坂井市で「かに祭り」開催\n"
              "\n### 2026-10-08\n\n- 10/24(土) 片町で「台南美食フェア」\n- 坂井市「かに祭り」の案内が出ている\n"
              "- 9/26・27 「テント市」開催\n- 10/17・18 「テント市」開催\n")
        items = odekake.parse_neta(md)
        names = [odekake._title(i) for i in items]
        self.assertEqual(names.count("台南美食フェア"), 1)
        self.assertEqual(names.count("かに祭り"), 1)
        self.assertEqual(names.count("テント市"), 2)
        self.assertEqual([i["written"] for i in items if odekake._title(i) == "台南美食フェア"], ["2026-10-15"])


class WeekendTest(unittest.TestCase):
    def test_weekend_of(self):
        for d in (date(2026, 10, 19), date(2026, 10, 23), date(2026, 10, 24), date(2026, 10, 25)):
            self.assertEqual(odekake.weekend_of(d), (date(2026, 10, 24), date(2026, 10, 25)))

    def test_weekend_page_splits_days(self):
        ev = lambda s, e, name, **k: {"kind": "催し", "start": s, "end": e, "area": "福井市",
                                      "text": f"「{name}」開催", "note": "", "source": None, **k}
        data = {"items": [ev("2026-10-24", "2026-10-25", "両日祭"), ev("2026-10-24", "2026-10-24", "土曜市"),
                          ev("2026-10-17", "2026-10-31", "飛び市", days=["2026-10-17", "2026-10-31"]),
                          ev("2026-10-25", "2026-10-25", "日曜会")]}
        html = odekake.render_weekend(data, date(2026, 10, 20))
        self.assertIn("両日祭", html)
        self.assertIn("土曜市", html)
        self.assertIn("日曜会", html)
        self.assertNotIn("飛び市", html)
        self.assertIn('<link rel="canonical" href="https://odekake.fukui-fukui.com/weekend/">', html)

    def test_pages_show_pr_box_for_organizers(self):
        # 主催者向けの PR 枠の案内（2026-10-22 代表「進めて」）。初回無料の一言も（同日 代表「進めて」）
        ev = {"kind": "催し", "start": "2026-10-24", "end": "2026-10-24", "area": "福井市",
              "text": "「土曜市」開催", "note": "", "source": None}
        wk = odekake.render_weekend({"items": [ev]}, date(2026, 10, 20))
        mo = odekake.render_month("2026-10", {"short": [ev], "long": []}, ["2026-10"], date(2026, 10, 4))
        self.assertIn('href="../submit/?from=weekend"', wk)
        self.assertIn('href="../../submit/?from=month"', mo)
        self.assertIn("主催者の方へ：PR枠のお申し込み", mo)
        self.assertIn("初めてのお申し込みは無料です。", mo)


class StayPageTest(unittest.TestCase):
    def test_stay_pages_and_links(self):
        # 泊まるのページ（2026-10-22 代表「1 OK」）：3軒以上の市町にページ、催しのカードに「近くに泊まる（PR）」
        hs = [{"id": i, "name": f"宿{i}", "city": "福井市" if i < 3 else "鯖江市", "area": "福井市", "features": ["温泉"],
               "url": f"https://a.r10.to/x{i}", "reviews": i, "rating": 4.0, "price": 5000, "checked": "2026-10-19"} for i in range(4)]
        odekake.HOTELS[:] = hs
        odekake.STAY_CITIES.clear(); odekake.STAY_CITIES.add("福井市")
        try:
            ev = {"kind": "催し", "start": "2026-10-24", "end": "2026-10-24", "area": "福井市",
                  "text": "「土曜市」開催", "note": "", "source": None}
            city = odekake.render_stay_city("福井市", hs[:3], {"items": [ev]}, date(2026, 10, 20))
            self.assertIn("福井市の宿・ホテル（3軒）", city)
            self.assertIn('rel="sponsored noopener"', city)
            self.assertIn("PR：このページの宿のリンクは", city)
            self.assertIn("土曜市", city)          # その市町のこれからの催し
            self.assertIn('"@type": "LodgingBusiness"', city)
            wk = odekake.render_weekend({"items": [ev]}, date(2026, 10, 20))
            self.assertIn("/stay/%E7%A6%8F%E4%BA%95%E5%B8%82/", wk)
            self.assertIn("福井市に泊まる（PR）", wk)
            idx = odekake.render_stay_index(hs, date(2026, 10, 20))
            self.assertIn("鯖江市（1軒）", idx)
        finally:
            odekake.HOTELS[:] = []
            odekake.STAY_CITIES.clear()


class SpotPageTest(unittest.TestCase):
    def test_spot_page_lists_recent_shops_newest_first(self):
        sp = lambda d, name: {"kind": "スポット", "start": d, "end": d, "area": "福井市", "text": f"「{name}」がオープン",
                              "note": "", "source": None, "instagram": "https://www.instagram.com/x/"}
        data = {"items": [sp("2026-10-01", "新しい店"), sp("2026-10-30", "これから店"), sp("2025-01-01", "古い店")]}
        html = odekake.render_spot(data, date(2026, 10, 20))
        self.assertIn("これから店", html)
        self.assertNotIn("古い店", html)
        self.assertLess(html.index("これからオープン"), html.index("2026年10月にオープン"))
        self.assertIn("お店の Instagram を見る", html)
        self.assertIn('"@type": "LocalBusiness"', html)


class AreaPageTest(unittest.TestCase):
    def test_area_items_skip_ended_and_old(self):
        ev = lambda s, e, a: {"kind": "催し", "start": s, "end": e, "area": a, "text": f"{s}「祭」開催", "note": "", "source": None}
        data = {"items": [ev("2026-10-01", "2026-10-02", "福井市"), ev("2026-10-24", "2026-10-24", "福井市"),
                          {"kind": "スポット", "start": "2026-10-01", "end": "2026-10-01", "area": "福井市",
                           "text": "「店」がオープン", "note": "", "source": None}]}
        g = odekake._area_items(data, date(2026, 10, 20))
        self.assertEqual((len(g["福井市"]["events"]), len(g["福井市"]["shops"])), (1, 1))
        html = odekake.render_area("福井市", g["福井市"], date(2026, 10, 20))
        self.assertIn('<link rel="canonical" href="https://odekake.fukui-fukui.com/area/%E7%A6%8F%E4%BA%95%E5%B8%82/">', html)
        self.assertIn("今週末", html)


class FormPageTest(unittest.TestCase):
    def test_contact_and_submit_pages(self):
        c = odekake.render_contact(date(2026, 10, 20))
        for k in ('name="type" value="inquiry"', 'name="website"', 'name="opened"', 'name="agree"', odekake.FORM_URL):
            self.assertIn(k, c)
        s = odekake.render_submit(date(2026, 10, 20))
        self.assertIn("主催者の方からのみ受け付けます", s)
        self.assertIn('name="agree_flyer"', s)
        self.assertIn('name="flyer"', s)
        self.assertNotIn("お約束するものではありません", s)
