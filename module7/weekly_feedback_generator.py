"""
Module 7: 週報告回饋生成器
處理週數據並調用LLM生成4個角色的週報回饋
"""

import json
import sys
import os
from pathlib import Path
from typing import Dict, List, Optional, Any

# 添加shared目錄到路徑
sys.path.append(str(Path(__file__).parent.parent / "shared"))

from character_prompts import (
    format_mego_weekly_feedback,
    format_leo_weekly_feedback,
    format_brian_weekly_feedback,
    format_doris_weekly_feedback
)


class WeeklyFeedbackGenerator:
    """週報回饋生成器 - 處理數據並生成prompt"""

    def __init__(self, painpoint_path: str = None):
        """
        初始化

        Args:
            painpoint_path: painpoint.json文件路徑
        """
        if painpoint_path is None:
            painpoint_path = str(Path(__file__).parent.parent / "shared" / "painpoint.json")

        with open(painpoint_path, 'r', encoding='utf-8') as f:
            self.painpoint_map = json.load(f)

    def parse_user_goals(self, user_goal_str: str) -> List[str]:
        """
        解析用戶目標字符串

        Args:
            user_goal_str: 如 "變健美, 睡得好"

        Returns:
            目標列表 ["變健美", "睡得好"]
        """
        if not user_goal_str:
            return []
        return [g.strip() for g in user_goal_str.split(',') if g.strip()]

    def parse_specific_goals(self, specific_goal_str: str) -> List[str]:
        """
        解析具體子目標字符串

        Args:
            specific_goal_str: 如 "緊實手臂, 強健腿部, 運動不累"

        Returns:
            子目標列表
        """
        if not specific_goal_str:
            return []
        # 如果已經是list，直接返回
        if isinstance(specific_goal_str, list):
            return specific_goal_str
        # 如果是字符串，按逗號分割
        return [g.strip() for g in specific_goal_str.split(',') if g.strip()]

    def parse_json_data(self, json_str: str) -> Dict:
        """
        解析JSON數據字符串

        Args:
            json_str: JSON格式的數據字符串

        Returns:
            解析後的dict對象
        """
        try:
            # 移除可能的```json和```標記
            cleaned = json_str.strip()
            if cleaned.startswith('```json'):
                cleaned = cleaned[7:]
            if cleaned.startswith('```'):
                cleaned = cleaned[3:]
            if cleaned.endswith('```'):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()

            # 優先嘗試直接解析（如果JSON已經是正確格式）
            try:
                return json.loads(cleaned)
            except json.JSONDecodeError:
                # 如果直接解析失敗，才進行修復
                pass

            # 修復JSON格式：使用狀態機方法逐字符處理
            import re

            # 簡單的方法：一次處理一個模式，從最特定到最通用

            # Step 1: 找到所有的鍵並加引號 (在:前面的單詞)
            # 匹配 {, [, 或逗號後面的key
            cleaned = re.sub(r'([,{\[]\s*)(\w+)\s*:', r'\1"\2":', cleaned)

            # Step 1.5: 修復 "records":   {" 應該是 "records": [{" 的問題
            # Doris案例中records是數組，但CSV缺少開頭的 [
            cleaned = re.sub(r'"records":\s+\{', r'"records": [{', cleaned)
            # 同時需要在最後加上 ]
            # 找到 records 數組結束的位置（最後一個 } 之前）
            if '"records": [{' in cleaned:
                # 在最後一個 } 前面的倒數第二個 } 後加上 ]
                parts = cleaned.rsplit('}', 2)
                if len(parts) == 3:
                    cleaned = parts[0] + '}]' + parts[1] + '}' + parts[2]

            # Step 2: 處理特定類型的值
            # 2a. Timestamp (ISO 8601格式)
            cleaned = re.sub(r':\s*(\d{4}-\d{2}-\d{2}T[\d:+-]+)(?=\s*[,}])', r': "\1"', cleaned)

            # 2b. 含中文的字串值（需要先處理，因為可能包含逗號）
            # 策略：匹配從 : 開始到下一個 "key": 或 } 之前的內容
            # 如果包含中文，就認為是字串值
            def fix_chinese_value(match):
                value = match.group(1).strip()
                # 如果已經有引號了，跳過
                if value.startswith('"') and value.endswith('"'):
                    return match.group(0)
                # 如果是null/true/false，跳過
                if value in ['null', 'true', 'false']:
                    return match.group(0)
                # 如果是純數字，跳過
                if re.match(r'^-?\d+\.?\d*$', value):
                    return match.group(0)
                # 否則加上引號
                return f': "{value}"'

            # 匹配 : 後面到下一個, \"key\": 或} 之前包含中文的內容
            cleaned = re.sub(
                r':\s*([^":\[\]{}][^:{}]*?[\u4e00-\u9fa5][^:{}]*?)(?=\s*,\s*"|\s*})',
                fix_chinese_value,
                cleaned
            )

            # 2c. 單個英文單詞值（如event_type）
            cleaned = re.sub(r':\s*([a-z_]+)(?=\s*[,}\]])', r': "\1"', cleaned)

            # Step 3: 清理被誤加引號的特殊值和數字
            cleaned = cleaned.replace('": "null"', '": null')
            cleaned = cleaned.replace('": "true"', '": true')
            cleaned = cleaned.replace('": "false"', '": false')
            cleaned = re.sub(r'": "(-?\d+\.?\d*)"', r'": \1', cleaned)

            # Debug: print cleaned JSON (comment out in production)
            # print("Cleaned JSON:", cleaned[:500])

            return json.loads(cleaned)
        except json.JSONDecodeError as e:
            print(f"JSON解析錯誤: {e}")
            print(f"原始字符串: {json_str[:200]}...")
            print(f"清理後的字符串: {cleaned[:300]}...")
            return {}

    def generate_mego_weekly_feedback(
        self,
        user_goal: str,
        json_data: str
    ) -> str:
        """
        生成Mego週報回饋prompt

        Args:
            user_goal: 用戶目標字符串 (如 "變健美, 睡得好")
            json_data: JSON格式的週數據

        Returns:
            完整的prompt或"FALLBACK_SCRIPT"
        """
        user_goals = self.parse_user_goals(user_goal)
        data = self.parse_json_data(json_data)

        # 提取records數據
        records = data.get('data', {}).get('records', {})

        return format_mego_weekly_feedback(
            user_goals=user_goals,
            records=records,
            painpoint_map=self.painpoint_map
        )

    def generate_leo_weekly_feedback(
        self,
        user_goal: str,
        specific_goal: str,
        json_data: str
    ) -> str:
        """
        生成豹哥週報回饋prompt

        Args:
            user_goal: 主要目標 (如 "變健美, 體力好")
            specific_goal: 具體子目標 (如 "緊實手臂, 強健腿部, 運動不累")
            json_data: JSON格式的週數據

        Returns:
            完整的prompt
        """
        user_goals = self.parse_user_goals(user_goal)
        specific_goals = self.parse_specific_goals(specific_goal)
        data = self.parse_json_data(json_data)

        # 提取records數據
        records = data.get('data', {}).get('records', {})

        return format_leo_weekly_feedback(
            user_goals=user_goals,
            specific_goals=specific_goals,
            records=records
        )

    def generate_brian_weekly_feedback(
        self,
        user_goal: str,
        specific_goal: str,
        json_data: str
    ) -> str:
        """
        生成冥想大師週報回饋prompt

        Args:
            user_goal: 主要目標 (如 "舒緩壓力, 睡得好")
            specific_goal: 具體子目標 (如 "清晰的思緒, 一覺到天亮")
            json_data: JSON格式的週數據

        Returns:
            完整的prompt
        """
        user_goals = self.parse_user_goals(user_goal)
        specific_goals = self.parse_specific_goals(specific_goal)
        data = self.parse_json_data(json_data)

        # 提取records數據
        records = data.get('data', {}).get('records', {})

        return format_brian_weekly_feedback(
            user_goals=user_goals,
            specific_goals=specific_goals,
            records=records
        )

    def generate_doris_weekly_feedback(
        self,
        user_goal: str,
        json_data: str
    ) -> str:
        """
        生成快煮鴨週報回饋prompt

        Args:
            user_goal: 用戶目標 (如 "變健美, 舒緩壓力")
            json_data: JSON格式的週數據

        Returns:
            完整的prompt或"FALLBACK_SCRIPT"
        """
        user_goals = self.parse_user_goals(user_goal)
        data = self.parse_json_data(json_data)

        # 提取數據
        tdee = data.get('data', {}).get('tdee', 2000)
        records = data.get('data', {}).get('records', [])

        return format_doris_weekly_feedback(
            user_goals=user_goals,
            tdee=tdee,
            records=records,
            painpoint_map=self.painpoint_map
        )

    def identify_character(self, json_data: str) -> str:
        """
        識別JSON數據中的角色

        Args:
            json_data: JSON格式的數據字符串

        Returns:
            角色名稱: "mego", "leo", "brian", "doris"
        """
        data = self.parse_json_data(json_data)
        character = data.get('character', '').lower()

        # 處理別名
        if character in ['mego', 'megaluki']:
            return 'mego'
        elif character in ['leo', '豹哥']:
            return 'leo'
        elif character in ['brian', '冥想大師', 'sloth']:
            return 'brian'
        elif character in ['doris', '快煮鴨', 'kuaizhuya']:
            return 'doris'
        else:
            return character


# 使用範例
if __name__ == "__main__":
    generator = WeeklyFeedbackGenerator()

    # 測試Mego週報生成
    print("=== 測試 Mego 週報回饋 ===")
    mego_data = """```json
    {
      "user_id": 12345,
      "session_id": null,
      "character": "mego",
      "timestamp": "2025-10-06T15:30:00+08:00",
      "event_type": "weekly_summary",
      "data": {
        "primary_goal": "變健美, 睡得好",
        "records": {
          "average_step": 8421,
          "average_step_goal": 8000,
          "step_goal_met_times": 5,
          "average_sleep_minutes": 410.5,
          "average_sleep_minutes_goal": 420.0,
          "sleep_minutes_goal_met_times": 4,
          "average_deep_sleep_minutes": 95.3,
          "achievement_count": 6
        }
      }
    }```"""

    mego_prompt = generator.generate_mego_weekly_feedback(
        user_goal="變健美, 睡得好",
        json_data=mego_data
    )
    print(mego_prompt[:500])
    print("\n" + "="*50 + "\n")

    # 測試Leo週報生成
    print("=== 測試 Leo 週報回饋 ===")
    leo_data = """{
      "user_id": 24680,
      "character": "leo",
      "data": {
        "primary_goal": "變健美, 體力好",
        "specific_goal": "緊實手臂, 強健腿部, 運動不累",
        "records": {
          "average_step": 10234,
          "average_step_goal": 9500,
          "step_goal_met_times": 6,
          "exercise_courses": "全身體能訓練, 入門燃脂運動, 躺姿伸展運動",
          "exercise_muscle_groups": "核心肌群, 大腿肌群, 背部"
        }
      }
    }"""

    leo_prompt = generator.generate_leo_weekly_feedback(
        user_goal="變健美, 體力好",
        specific_goal="緊實手臂, 強健腿部, 運動不累",
        json_data=leo_data
    )
    print(leo_prompt[:500])
    print("\n" + "="*50 + "\n")
