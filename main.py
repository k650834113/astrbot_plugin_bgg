from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
import astrbot.api.message_components as Comp
import aiohttp
import xml.etree.ElementTree as ET


@register("bgg", "KisaragiIzumi", "接入BGG API插件", "1.0.0")
class BGGPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.api_base = "https://boardgamegeek.com/xmlapi2"

    async def initialize(self):
        """可选择实现异步的插件初始化方法，当实例化该插件类之后会自动调用该方法。"""

    # 注册指令的装饰器。指令名为 桌游查询。注册成功后，发送 `/桌游查询 游戏名` 就会触发这个指令，并回复 桌游相关详情
    @filter.command("桌游查询")
    async def 桌游查询(self, event: AstrMessageEvent, game: str):
        """查询桌游信息 指令`/桌游查询 游戏名`或`/桌游查询 游戏ID`"""  # 这是 handler 的描述，将会被解析方便用户了解插件内容。建议填写。

        # 判断输入是ID还是名称
        if game.isdigit():
            result = await self.fetch_game_by_id(game)
        else:
            result = await self.search_game_by_name(game)
        yield event.chain_result(result)

    async def terminate(self):
        """可选择实现异步的插件销毁方法，当插件被卸载/停用时会调用。"""

    # === BGG API 交互层 ===
    async def fetch_game_by_id(self, game_id: str) -> list[Comp.BaseMessageComponent]:
        """通过ID获取桌游基础信息"""
        Chain = []
        async with aiohttp.ClientSession() as session:
            url = f"{self.api_base}/thing?id={game_id}&stats=1"
            logger.info("开始查询详细信息")
            async with session.get(url) as resp:
                if resp.status != 200:
                    Chain.append(Comp.Plain(text="查询失败，请检查ID或重试"))
                    return Chain
                xml_data = await resp.text()
                return self.parse_basic_xml(xml_data)

    def parse_basic_xml(self, xml_str: str) -> list[Comp.BaseMessageComponent]:
        """解析基础信息XML"""
        Chain = []
        root = ET.fromstring(xml_str)
        item = root.find(".//item[@type='boardgame']")
        item_type = "桌游"
        if item is None:
            item = root.find(".//item[@type='boardgameexpansion']")
            item_type = "扩展"
            if item is None:
                Chain.append(Comp.Plain(text="未找到匹配的桌游"))
                return Chain

        # 提取核心字段
        title = item.find(".//name[@type='primary']").get("value")
        year = item.find(".//yearpublished").get("value")
        players = (
            item.find(".//minplayers").get("value")
            + "-"
            + item.find(".//maxplayers").get("value")
        )
        bestplayers = (
            item.find(".//poll-summary[@name='suggested_numplayers']")
            .find(".//result[@name='bestwith']")
            .get("value")
        )
        rating = item.find(".//average").get("value")
        playtime = (
            item.find(".//minplaytime").get("value")
            + "-"
            + item.find(".//maxplaytime").get("value")
        )
        description = item.find(".//description").text.strip()  # 截断长描述
        description.replace('&#10;','\n')
        weight = item.find(".//averageweight").get("value")
        image = item.find(".//thumbnail").text.strip()

        Chain.append(Comp.Image(file=image))
        Chain.append(
            Comp.Plain(
                text=(
                    f"🎲 {item_type}：{title} ({year})\n"
                    f"👥 人数: {players} |最佳人数：{bestplayers} \n"
                    f"🕐时长：{playtime}\n"
                    f"⭐ 评分: {rating}/10\n"
                    f"📖 简介: {description}\n"
                    f"🧠复杂度：{weight}/5\n"
                    f"🌐 完整数据: https://boardgamegeek.com/boardgame/{item.get('id')}"
                )
            )
        )
        return Chain

    async def search_game_by_name(self, name: str) -> list[Comp.BaseMessageComponent]:
        """通过名称搜索桌游，返回匹配列表，再通过ID进行详细查询"""
        Chain = []
        logger.info("通过名称搜索")
        async with aiohttp.ClientSession() as session:
            url = f"{self.api_base}/search?query={name}&type=boardgame"
            logger.info("获取XML列表")
            async with session.get(url) as resp:
                if resp.status != 200:
                    Chain.append(Comp.Plain(text="搜索失败，请重试"))
                    return Chain
                xml_data = await resp.text()
                return await self.parse_search_xml(xml_data)

    async def parse_search_xml(self, xml_str: str) -> list[Comp.BaseMessageComponent]:
        """解析搜索结果XML"""
        Chain = []
        root = ET.fromstring(xml_str)
        items = root.findall(".//item")
        if not items:
            Chain.append(Comp.Plain(text="BGG中未找到相关桌游，请检查代理名称是否正确，或使用英文原名"))
            return Chain

        count = root.get("total")
        if int(count) == 1:
            id = items[0].get("id")
            logger.info("找到唯一ID{id}，直接查询详细信息")
            return await self.fetch_game_by_id(id)

        reply = "🔍 搜索结果：\n"
        for item in items:
            title = item.find("name").get("value")
            year = item.find("yearpublished").get("value") or "未知年份"
            reply += f"- {title} ({year}) | ID: {item.get('id')}\n"
        reply += "💡 输入 /桌游查询 ID 查看详情（如：/桌游查询 1234）"

        Chain.append(Comp.Plain(text=reply))
        return Chain
