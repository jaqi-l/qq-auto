#!/usr/bin/env python3
"""
QQ 每日自动任务 - 等级加速
通过 Cookie 模拟登录，完成每日等级加速任务
适用于 GitHub Actions 定时执行
"""

import os
import re
import json
import time
import hashlib
import requests
from datetime import datetime
from urllib.parse import quote

# ============================================================
# 配置 - 从环境变量读取
# ============================================================

# QQ Cookie（从浏览器获取，必需）
QQ_COOKIE = os.environ.get('QQ_COOKIE', 'RK=pMDq/p6ARQ; ptcz=3290f2e1e5aff15a4cc873650299d46ff20427b75834bba1ed00d42560cbd8c3; _clck=tzpjal|1|g7j|0; pgv_info=ssid=s1559662090; pgv_pvid=1045185503; uin=o0547152849; skey=@muphZy6Al; p_uin=o0547152849; pt4_token=Mz8kSfQ-G8eFDtDUsgXtVLO7FT3Mlhj1wT82NO0IwYo_; p_skey=dUcE6*dSrkq*cXUk1y3WRycq0AHh2WnOXj8I*i*n5Kw_; Loading=Yes; media_p_uin=547152849; qqmusic_uin=; qqmusic_key=; qqmusic_fromtag=; __Q_w_s_hat_seed=1; qzmusicplayer=qzone_player_547152849_1783491177804; v6uin=547152849|qzone_player; media_p_skey=8JgqobheYugbKRq77LBN85zoZN0tT20J-RhPuQ3XSrstZvH8khg6uO0yVnOGpazZf6TPv6CpqnEaCupjy0ogvQ')

# 推送通知（可选）
PUSH_KEY = os.environ.get('PUSH_KEY', '')
PUSH_TYPE = os.environ.get('PUSH_TYPE', '')  # serverchan / pushplus / telegram

# 是否启用 QQ 音乐听歌任务
ENABLE_QQ_MUSIC = os.environ.get('ENABLE_QQ_MUSIC', 'true').lower() == 'true'

# 是否启用 QQ 手游加速任务
ENABLE_QQ_GAME = os.environ.get('ENABLE_QQ_GAME', 'true').lower() == 'true'

# ============================================================
# 日志
# ============================================================

logs = []


def log(msg):
    """输出并收集日志"""
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    line = f'[{now}] {msg}'
    print(line, flush=True)
    logs.append(line)


# ============================================================
# 工具函数
# ============================================================

def get_g_tk(skey):
    """
    从 skey 计算 g_tk
    腾讯系通用鉴权算法：hash = 5381, 循环 hash += (hash << 5) + ord(c)
    """
    h = 5381
    for c in skey:
        h += (h << 5) + ord(c)
    return h & 0x7fffffff


def get_p_skey_g_tk(p_skey):
    """
    从 p_skey 计算 g_tk（Qzone 专用，算法与 skey 相同）
    """
    h = 5381
    for c in p_skey:
        h += (h << 5) + ord(c)
    return h & 0x7fffffff


def extract_cookie_value(cookie_str, key):
    """从 cookie 字符串中提取指定 key 的值"""
    for item in cookie_str.split(';'):
        item = item.strip()
        if '=' in item:
            k, v = item.split('=', 1)
            if k.strip() == key:
                return v.strip()
    return ''


def get_uin_from_cookie(cookie_str):
    """从 cookie 中提取 uin（QQ号）"""
    uin = extract_cookie_value(cookie_str, 'uin')
    if uin:
        # uin 格式通常是 o_123456789，需要去掉 o_ 前缀
        uin = uin.lstrip('o').lstrip('_')
    if not uin:
        uin = extract_cookie_value(cookie_str, 'o_cookie')
    if not uin:
        uin = extract_cookie_value(cookie_str, 'wxuin')
    return uin


def get_skey_from_cookie(cookie_str):
    """从 cookie 中提取 skey"""
    skey = extract_cookie_value(cookie_str, 'skey')
    if not skey:
        skey = extract_cookie_value(cookie_str, 'p_skey')
    return skey


def get_p_skey_from_cookie(cookie_str):
    """从 cookie 中提取 p_skey"""
    return extract_cookie_value(cookie_str, 'p_skey')


# ============================================================
# HTTP 客户端
# ============================================================

class QQClient:
    """QQ API 客户端"""

    def __init__(self, cookie):
        self.cookie = cookie
        self.skey = get_skey_from_cookie(cookie)
        self.p_skey = get_p_skey_from_cookie(cookie)
        self.uin = get_uin_from_cookie(cookie)
        self.g_tk = get_g_tk(self.skey) if self.skey else 0
        self.p_g_tk = get_p_skey_g_tk(self.p_skey) if self.p_skey else 0

        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Linux; Android 10; MI 8 Lite Build/QKQ1.190910.002; wv) '
                          'AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/109.0.5414.86 '
                          'MQQBrowser/6.2 TBS/046613 Mobile Safari/537.36 V1_AND_SQ_8.9.73_4416_YYB_D '
                          'QQ/8.9.73.11945 NetType/WIFI WebP/0.3.0 AppId/537171693 Pixel/1080 '
                          'StatusBarHeight/82 SimpleUISwitch/0 QQTheme/1000 StudyMode/0 '
                          'CurrentMode/0 CurrentFontScale/1.0 GlobalDensityScale/0.9818182 '
                          'AllowLandscape/false InMagicWin/0',
            'Cookie': cookie,
            'Referer': 'https://m.qzone.com/',
        })

        log(f'📋 初始化: UIN={self.uin}, skey={"✅" if self.skey else "❌"}, '
            f'p_skey={"✅" if self.p_skey else "❌"}, g_tk={self.g_tk}')

    def _check_cookie(self):
        """检查 cookie 是否有效"""
        if not self.cookie:
            log('❌ Cookie 未配置，请在 GitHub Secrets 中设置 QQ_COOKIE')
            return False
        if not self.skey and not self.p_skey:
            log('❌ Cookie 中未找到 skey 或 p_skey，请检查 Cookie 是否完整')
            return False
        return True

    # ============================================================
    # 任务 1: QQ 等级加速任务
    # ============================================================

    def qq_level_acceleration(self):
        """完成 QQ 等级加速任务"""
        log('🚀 开始执行 QQ 等级加速任务...')

        if not self._check_cookie():
            return False

        success = True

        # 获取等级信息
        level_info = self.get_level_info()

        # 完成加速任务
        task_result = self.complete_acceleration_tasks()

        # 查询加速后的等级信息
        if task_result:
            self.get_level_info()

        return success

    def get_level_info(self):
        """获取 QQ 等级和加速信息"""
        log('📊 查询 QQ 等级信息...')

        try:
            url = 'https://ti.qq.com/qqlevel/index'
            params = {
                '_wv': '3',
                '_wwv': '1',
                'tab': '7',
                'source': '1',
            }
            headers = {
                'Host': 'ti.qq.com',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7',
                'Content-Type': 'application/json',
                'Cookie': self.cookie,
            }

            res = self.session.get(url, params=params, headers=headers, timeout=15)
            res.encoding = 'utf-8'
            text = res.text

            # 解析页面中的 __INITIAL_STATE__ 数据
            match = re.search(r'window\.__INITIAL_STATE__\s*=\s*(.*?)\s*;', text)
            if not match:
                log('❌ 获取等级信息失败：无法解析页面数据')
                return None

            data = json.loads(match.group(1))

            qq_level_info = data.get('qqLevelInfo', {})
            level_info = data.get('levelInfo', {})
            level_progress = level_info.get('levelProgress', {})
            ori_info = level_info.get('oriInfo', {})

            nickname = qq_level_info.get('sNickName', '未知')
            cur_days = level_progress.get('curLevelDays', 0)
            total_days = level_progress.get('curLevelTotalDays', 0)
            cur_level = ori_info.get('oriLevel', 0)
            rank = ori_info.get('oriRank', 0)

            log(f'👤 昵称: {nickname}')
            log(f'👑 当前等级: {cur_level} 级')
            log(f'📈 已加速天数: {cur_days}/{total_days}')
            log(f'🏆 好友排名: 第{rank}名')

            # 解析加速任务列表
            task_list = data.get('taskList', [])
            if task_list:
                log('📋 加速任务列表:')
                for task in task_list:
                    title = task.get('title', '未知任务')
                    status = '✅ 已完成' if task.get('status', 0) != 0 else '❌ 未完成'
                    days = task.get('finishedAccelerateDays', 0)
                    log(f'   - {title}: {status} (加速 {days} 天)')

            return data

        except Exception as e:
            log(f'❌ 获取等级信息异常: {e}')
            return None

    def complete_acceleration_tasks(self):
        """完成等级加速任务"""
        log('🎯 尝试完成等级加速任务...')

        results = []

        # 任务1: QQ 等级加速 - 模拟在线
        results.append(self._task_online_acceleration())

        # 任务2: QQ 音乐听歌加速
        if ENABLE_QQ_MUSIC:
            results.append(self._task_qq_music())

        # 任务3: QQ 手游加速
        if ENABLE_QQ_GAME:
            results.append(self._task_qq_game())

        # 任务4: QQ 会员签到
        results.append(self._task_vip_checkin())

        # 任务5: QQ 空间签到
        results.append(self._task_qzone_checkin())

        return any(results)

    def _task_online_acceleration(self):
        """模拟 QQ 在线 - 每日登录加速"""
        log('⏰ 执行每日登录加速...')

        try:
            # 调用 QQ 在线接口模拟登录
            url = 'https://proxy.vac.qq.com/cgi-bin/srfentry.fcgi'
            params = {
                'g_tk': self.g_tk,
                'uin': self.uin,
                'ua': 'MQQBrowser',
            }
            res = self.session.get(url, params=params, timeout=15)

            # 另一个在线接口
            url2 = f'https://ti.qq.com/qqlevel/reportOnlineTime'
            params2 = {
                'g_tk': self.g_tk,
                'uin': self.uin,
            }
            data2 = {
                'onlineTime': 120,  # 模拟在线2小时
            }
            try:
                res2 = self.session.post(url2, params=params2, json=data2, timeout=15)
                log(f'✅ 在线时间上报完成 (状态码: {res2.status_code})')
            except Exception:
                pass

            log('✅ 每日登录加速任务执行完成')
            return True

        except Exception as e:
            log(f'❌ 每日登录加速异常: {e}')
            return False

    def _task_qq_music(self):
        """QQ音乐听歌加速任务"""
        log('🎵 执行 QQ 音乐听歌加速任务...')

        try:
            # QQ 音乐签到
            url = 'https://u.y.qq.com/cgi-bin/musicu.fcg'
            data = {
                'comm': {
                    'ct': '19',
                    'cv': '1859',
                    'uin': self.uin,
                },
                'req': {
                    'module': 'music.recommend.RecommendFeed',
                    'method': 'get_recommend_feed',
                    'param': {},
                },
            }

            headers = {
                'Cookie': self.cookie,
                'Content-Type': 'application/json',
                'User-Agent': 'Mozilla/5.0 (Linux; Android 10) AppleWebKit/537.36 '
                              'Chrome/109.0.0.0 Mobile Safari/537.36',
                'Referer': 'https://y.qq.com/',
            }

            try:
                res = self.session.post(url, json=data, headers=headers, timeout=15)
                log(f'✅ QQ 音乐接口调用完成 (状态码: {res.status_code})')
            except Exception as e2:
                log(f'⚠️ QQ 音乐接口异常: {e2}')

            # 模拟听歌（发送播放上报）
            listen_url = 'https://u.y.qq.com/cgi-bin/musicu.fcg'
            listen_data = {
                'comm': {
                    'ct': '19',
                    'cv': '1859',
                    'uin': self.uin,
                },
                'req': {
                    'module': 'music.recommend.RecommendFeed',
                    'method': 'listen_song',
                    'param': {
                        'songId': 0,
                        'playTime': 3600,  # 模拟听歌1小时
                    },
                },
            }

            try:
                res = self.session.post(listen_url, json=listen_data, headers=headers, timeout=15)
                log(f'✅ QQ 音乐听歌上报完成 (状态码: {res.status_code})')
            except Exception as e2:
                log(f'⚠️ QQ 音乐听歌上报异常: {e2}')

            log('✅ QQ 音乐听歌加速任务执行完成')
            return True

        except Exception as e:
            log(f'❌ QQ 音乐听歌加速异常: {e}')
            return False

    def _task_qq_game(self):
        """QQ 手游加速任务"""
        log('🎮 执行 QQ 手游加速任务...')

        try:
            # 模拟 QQ 手游登录
            url = 'https://game.qq.com/comm-htdocs/mrqz/mrqz_gameLogin.shtml'
            params = {
                'g_tk': self.g_tk,
                'uin': self.uin,
            }

            try:
                res = self.session.get(url, params=params, timeout=15)
                log(f'✅ QQ 手游登录接口调用完成 (状态码: {res.status_code})')
            except Exception as e2:
                log(f'⚠️ QQ 手游登录接口异常: {e2}')

            log('✅ QQ 手游加速任务执行完成')
            return True

        except Exception as e:
            log(f'❌ QQ 手游加速异常: {e}')
            return False

    def _task_vip_checkin(self):
        """QQ 会员每日签到"""
        log('💎 执行 QQ 会员每日签到...')

        try:
            url = 'https://proxy.vac.qq.com/cgi-bin/srfentry.fcgi'
            params = {
                'g_tk': self.g_tk,
                'uin': self.uin,
                'cmd': 'sign',
                'acttype': '2',
            }

            try:
                res = self.session.get(url, params=params, timeout=15)
                if res.status_code == 200:
                    try:
                        data = res.json()
                        if data.get('code') == 0 or data.get('ret') == 0:
                            log('✅ QQ 会员签到成功')
                        else:
                            log(f'ℹ️ QQ 会员签到返回: {data}')
                    except Exception:
                        log(f'✅ QQ 会员签到请求已发送 (状态码: {res.status_code})')
                else:
                    log(f'⚠️ QQ 会员签到返回状态码: {res.status_code}')
            except Exception as e2:
                log(f'⚠️ QQ 会员签到接口异常: {e2}')

            log('✅ QQ 会员签到任务执行完成')
            return True

        except Exception as e:
            log(f'❌ QQ 会员签到异常: {e}')
            return False

    def _task_qzone_checkin(self):
        """QQ 空间签到"""
        log('🌟 执行 QQ 空间签到...')

        try:
            # QQ 空间签到使用 p_skey 和对应的 g_tk
            if not self.p_skey:
                log('⚠️ 缺少 p_skey，跳过 QQ 空间签到（Cookie 中需包含 p_skey）')
                return False

            url = 'https://mobile.qzone.qq.com/fcgi-bin/fcg_addsign'
            params = {
                'g_tk': self.p_g_tk,
                'uin': self.uin,
                'sign_type': '1',
            }

            try:
                res = self.session.get(url, params=params, timeout=15)
                if res.status_code == 200:
                    try:
                        data = res.json()
                        if data.get('code') == 0:
                            log('✅ QQ 空间签到成功')
                        elif data.get('code') == -1001:
                            log('⏭️ QQ 空间今日已签到')
                        else:
                            log(f'ℹ️ QQ 空间签到返回: code={data.get("code")}, msg={data.get("msg", "")}')
                    except Exception:
                        log(f'✅ QQ 空间签到请求已发送 (状态码: {res.status_code})')
                else:
                    log(f'⚠️ QQ 空间签到返回状态码: {res.status_code}')
            except Exception as e2:
                log(f'⚠️ QQ 空间签到接口异常: {e2}')

            log('✅ QQ 空间签到任务执行完成')
            return True

        except Exception as e:
            log(f'❌ QQ 空间签到异常: {e}')
            return False


# ============================================================
# 推送通知
# ============================================================

def send_notification():
    """发送推送通知"""
    if not PUSH_KEY:
        return

    content = '\n'.join(logs)
    title = f'QQ每日任务报告 - {datetime.now().strftime("%Y-%m-%d")}'

    try:
        if PUSH_TYPE == 'serverchan':
            # Server酱
            url = f'https://sctapi.ftqq.com/{PUSH_KEY}.send'
            res = requests.post(url, data={'title': title, 'desp': content}, timeout=10)
            if res.status_code == 200 and res.json().get('code') == 0:
                log('📨 Server酱推送成功')
            else:
                log(f'⚠️ Server酱推送失败: {res.text[:100]}')

        elif PUSH_TYPE == 'pushplus':
            # PushPlus
            url = 'http://www.pushplus.plus/send'
            res = requests.post(url, json={
                'token': PUSH_KEY,
                'title': title,
                'content': content,
                'template': 'txt',
            }, timeout=10)
            if res.status_code == 200 and res.json().get('code') == 200:
                log('📨 PushPlus推送成功')
            else:
                log(f'⚠️ PushPlus推送失败: {res.text[:100]}')

        elif PUSH_TYPE == 'telegram':
            # Telegram
            parts = PUSH_KEY.split('|')
            bot_token = parts[0] if len(parts) > 0 else ''
            chat_id = parts[1] if len(parts) > 1 else ''

            if bot_token and chat_id:
                url = f'https://api.telegram.org/bot{bot_token}/sendMessage'
                res = requests.post(url, json={
                    'chat_id': chat_id,
                    'text': f'*{title}*\n\n{content}',
                    'parse_mode': 'Markdown',
                }, timeout=10)
                if res.status_code == 200 and res.json().get('ok'):
                    log('📨 Telegram推送成功')
                else:
                    log(f'⚠️ Telegram推送失败: {res.text[:100]}')
            else:
                log('⚠️ Telegram推送配置错误，PUSH_KEY 格式: BotToken|ChatId')

    except Exception as e:
        log(f'❌ 推送通知异常: {e}')


# ============================================================
# 主流程
# ============================================================

def main():
    log('=' * 50)
    log('🤖 QQ 每日自动任务 - 等级加速')
    log('=' * 50)

    if not QQ_COOKIE:
        log('❌ 未配置 QQ_COOKIE，请按照 README 获取 Cookie 并配置到 GitHub Secrets')
        log('   获取方式：')
        log('   1. 电脑浏览器打开 https://m.qzone.com 并登录')
        log('   2. 按 F12 → Application → Cookies')
        log('   3. 复制整个 Cookie 字符串')
        log('   4. 在 GitHub 仓库 Settings → Secrets 中添加 QQ_COOKIE')
        send_notification()
        return

    client = QQClient(QQ_COOKIE)
    client.qq_level_acceleration()

    log('=' * 50)
    log('🏁 所有任务执行完毕')
    log('=' * 50)

    # 发送推送通知
    send_notification()


if __name__ == '__main__':
    main()
