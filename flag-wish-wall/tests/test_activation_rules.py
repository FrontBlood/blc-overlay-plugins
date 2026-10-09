import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import main


async def run_test():
    original_records_path = main.RECORDS_PATH
    original_config_path = main.CONFIG_PATH
    test_records_path = Path(__file__).with_name("_activation_records_test.json")
    test_config_path = Path(__file__).with_name("_activation_config_test.json")
    test_records_path.unlink(missing_ok=True)
    test_config_path.write_text('{"flag":"Flag","secondary_flag":"Wish"}', encoding="utf-8")
    try:
        main.CONFIG_PATH = test_config_path
        migrated = main.load_config()
        assert migrated["secondary_flags"] == ["Wish"]
        assert "secondary_flag" not in migrated

        main.RECORDS_PATH = test_records_path
        config = {
            **main.DEFAULT_CONFIG,
            "flag": "Flag",
            "secondary_flags": ["愿望", "许愿", "Wish", "上舰"],
            "secondary_auto_publish": False,
            "min_medal_level": 0,
        }
        store = main.RecordStore(200)
        app = main.FlagRecordApp(store, config)

        primary, reason = await app.accept_danmaku("1", "A", "fLaG主词内容，另有愿望", 0)
        assert reason == "recorded"
        assert primary["activation"] == "primary"
        assert primary["published"] is True
        assert len(store.records) == 1, "one danmaku must create only one record"

        secondary, reason = await app.accept_danmaku("2", "B", "聊天中Flag不算主词，愿望副词内容", 0)
        assert reason == "pending_review"
        assert secondary["activation"] == "secondary"
        assert secondary["published"] is False
        assert [item["id"] for item in store.snapshot(published_only=True)] == [primary["id"]]

        ignored, reason = await app.accept_danmaku("3", "C", "聊天中只有FLAG", 0)
        assert ignored is None and reason == "missing_flag"

        approved = await store.publish(secondary["id"])
        assert approved["published"] is True
        assert len(store.snapshot(published_only=True)) == 2

        config["secondary_auto_publish"] = True
        automatic, reason = await app.accept_danmaku("4", "D", "我有一个愿望自动发布", 0)
        assert reason == "recorded"
        assert automatic["activation"] == "secondary" and automatic["published"] is True

        another, reason = await app.accept_danmaku("5", "E", "今天想要许愿第二个副词", 0)
        assert reason == "recorded"
        assert another["content"] == "今天想要许愿第二个副词"

        casefolded, reason = await app.accept_danmaku("6", "F", "I WISH everything works", 0)
        assert reason == "recorded"
        assert casefolded["content"] == "I WISH everything works"

        one_record, reason = await app.accept_danmaku("7", "G", "Wish先出现，随后许愿也出现", 0)
        assert reason == "recorded"
        assert one_record["content"] == "Wish先出现，随后许愿也出现"
        assert len([item for item in store.records if item["uid"] == "7"]) == 1

        punctuation, reason = await app.accept_danmaku("8", "H", "今天我想上舰！", 0)
        assert reason == "recorded"
        assert punctuation["content"] == "今天我想上舰！"

        assert main.parse_flag_content("FLAGMixedCase", "Flag", 0, at_start=True) == "MixedCase"
        assert main.parse_flag_content("前缀Flag内容", "Flag", 0, at_start=True) is None
    finally:
        main.RECORDS_PATH = original_records_path
        main.CONFIG_PATH = original_config_path
        test_records_path.unlink(missing_ok=True)
        test_config_path.unlink(missing_ok=True)


if __name__ == "__main__":
    asyncio.run(run_test())
    print("activation priority and moderation tests passed")
