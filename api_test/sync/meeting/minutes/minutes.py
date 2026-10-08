# -*- coding: utf-8 -*-
"""请求 minutes 接口并解析返回字段。用法：python minutes.py

统一入口：POST /api/agent/v1，域与任务名在请求体（"domain": "meeting", "task": "minutes"）。
"""
import os
import uuid

import requests

# ── 会议转写文本（三引号内直接粘贴）──
TRANSCRIPT = """
• 发言者 1 00:21
最近呢霍伊斯根主席各位朋友，各位同事，我们所处的是一个更加变乱交织的世界。大家都关心这个世界今后向何处去。借用今年慕安会报告的主题来回答的话，那就是走向多极化。80年前联合国成立时，只有51个会员国，到今天是193个国家，共乘一艘大船。多极化的世界既是历史的必然，也正在成为现实。多极化是否会带来动荡失序，冲突对抗是否意味着大国主导弱肉强食。中国给出的答案是我们应当推动平等有序的世界多极化。这是习近平主席提出的又一个重大主张，也是我们对多极世界真诚的期许。中国必将是多极体系中的确定性因素。将坚定做变革世界中的建设性力量。在此我表达4点看法。一是应当倡导平等相待，列强争霸曾给人类带来灾难。两次世界大战殷鉴不远，殖民体系也罢，
• 发言者 1 01:58
中心外围体系也罢，不平等的秩序注定土崩瓦解。世界各国独立自主，风起云涌，国际关系民主法不可阻挡。坚持权利平等机会平等规则平等，应当成为建设多极世界的基本原则。正是秉+D5持这样的原则，中国主张大小国家一律平等，呼吁提升发展中国家在国际体系中的代表性和发言权。这不会导致西方的缺失，而将促进世界的正和慕安会近年来邀请更多全球南方国家出席会议，这是明智之举。每一个国家的声音都应该得到倾听。每一个国家都可以在多极格局中找到自身的位置，发挥自己的作用。二是应当尊重国际法治。中国有句古话没有规矩不成方圆，
• 发言者 1 03:06
联合国宪章宗旨和原则是处于国际关系的根本遵循。也是建设多极世界的重要基石。当今世界乱象频出，一个重要原因就是有些国家迷信实力至上，打开了丛林法则的潘多拉盒子。实际上国家不论大小强弱，都是国际法治的利益攸关法。多极格局不能是无序的状态。如果没有了规矩，昨天在餐桌上明天就可能在菜单里大国要带头讲诚信，讲法治，坚决摒弃言行不一。零和博弈。正是基于这样的观点，中国坚定维护国际法治权威，积极履行国际责任和义务。我们加入了几乎所有普遍性的政府间国际组织和600多项国际公约。我们从不搞例外主义，
• 发言者 1 04:18
更不搞合则用，不合则弃。我们为当今不确定的世界提供了最大的确定性。我要强调的是在遵守国际法上不能搞双重标准，要尊重各国的主权和领土完整，就应该支持中国实现完全统一。三是要践行多边主义。面对层出不穷的全球性挑战，没有哪一个国家能够独善其身，搞本国优先只会造成各方的多数。联合国是践行多边主义，推进全球治理的核心平台。已经为各国遮风挡雨。80年。未来的多极世界更加需要联合国对于这座大厦，我们应该固本强基，而不是拆梁毁柱。对于治理全球难题应当共担责任，
• 发言者 1 05:23
而不是唯利是图。对于共同挑战应该团结应对，而不是阵营对抗。正是本着这样的理念，中国坚持真正的多边主义，倡导共商共建共享的全球治理观。我们坚定维护联合国的权威和地位，承担着超过20%的联合国的会费。我们切实履行巴黎协定，建成了世界上最大的清洁发电体系。我们还提出并落实全球发展倡议，全球安全倡议全球文明倡议，为完善全球治理提供公共产品。4是要坚持开放共赢。发展是破解各种难题的钥匙，多极世界应该是各国共同发展的世界。保护主义不是出路，
• 发言者 1 06:28
滥加关税没有赢家。脱钩断链断的是机遇，小院高墙封的是自己。应当坚持开放合作，以普惠包容的经济全球化。来支撑平等有序的世界多极化。正是朝着这样的目标，中国坚定同各国共享发展机遇。有位澳大利亚的学者把中国称为赋能型大国，我认为很形象。去年中国GDP增长5%，对世界经济增长的贡献率接近30%。我们担当起全球经济增长的重要引擎，我们向世界释放超大规模的市场红利。中国愿推动高质量共建一带一路，而且同欧盟的门户全球门户的战略相互对接。赋能彼此也赋能世界。各位朋友，
• 发言者 1 07:38
中方始终认为欧洲是多极世界的重要一极。中欧双方是伙伴而不是对手。今年是中欧建交50周年，中方愿意同欧方用好这一契机，深化战略沟通和互利合作，推动世界走向和平。安全繁荣进步的光明前景。谢谢各位。
• 发言者 2 08:44
Thankvery much and director wang yi for your speech and also thanking for clinging to the10min. Appreciate that. You mentioned the international order, and this is something thatalso in my introductory remarks, I highlighted the need to respect the un charter and喂see nowa IoT of questioning of this.
• 发言者 2 09:08
喂seerussia invadingukraine.We haveseenfrom the americanPresident.These last weeks,where he threatened to use forceinvading greenland and panama andalso the the displacement of palestiniansand your country.Has been also accused of violating the law of the sea or also the universal declaration of human rights.
• 发言者 2 09:34
Now you are traveling from here to new york to the security council. Do you continue to believe in the united nations? Do you believe in the charter of the un?and will you work also for reform of the un? The un charter? How high is that on your priority?
• 发言者 1 10:03
嗯。我不愿意回答。周琦先生的提问，你的提问当中大概涉及到两个关键词，一个是秩序，一个是规则。那么说到秩序，这几年总有人说中国要改变秩序，中国要另起炉灶，但是我想现在再说这种话的人可能不会太多了。因为真正要挑战秩序，在毁约退群的国家出现了尤其欧洲的朋友们，你可能每天都在感受到阵阵袭来的寒意。而中国我们是在现行国际秩序中发展起来的，我们是这个秩序的受益者。我们要做的就是按照大多数国家的愿望，推动这个秩序朝着更加公正合理的方向去发展。谈到规则，大家可能对规则有不同的理解。但是我认为我们起码应该有一个共同的认知，
• 发言者 1 11:16
那就是我们需要共同来维护。以联合国为核心的国际体系。共同遵守以联合国宪章宗旨和原则为基础的国际关系的基本准则。我想这应该是我们的最大的公约数。只要我们大家都认同这一点，有些人所说的双重标准就不会出现了，没有它存在的空间。很多重大的地区热点问题，就像刚才朱医生所谈到的，我们都有了判断的。同样的标准，中国意识到我们承担的国际责任和义务，我们愿意向世界提供更多的公共产品。习近平主席提出了一系列重大的倡议和主张，包括我刚才提到的全球发展倡议，全球安全倡议。全球文明倡议，我们是希望国际社会能够携起手来，共同来解决好当今日益严重的发展赤字。安全赤字，
• 发言者 1 12:40
还有治理赤字。习主席还提出了一个重大的理念，那就是我们各国一起共同构建人类命运共同体。这是一个宏伟的目标。那么我们希望各国都能够超越历史文化社会制度意识形态的这种不同。我们以同舟共济的精神，共同来呵护好我们这个唯一人类可以居住的星球，我们共同来建设好命运与共的地球村。这既是我们中国我们共产党的国际主义的一种情怀，也是体现了天下为公。这一中华民族的优秀的文化的传统，已经得到了越来越多国家的理解认同和支持。而中国我们将会继续为践行好这些重要的理念来做出我们的努力。和贡献。
• 发言者 1 13:56
谢谢。
• 发言者 2 14:01
One of the topics here since22has been russia's invasion of ukraineat the msc just a few days before russia'sinvasion,you stated and I quoteThe sovereignty, independence and territorial integrity of any country should be respected and safeguarded because IT is a basic norm of international relations. Ukraine is no exception, so you confirmed the charter of the united nations now.Today,russia has become whatJohn mccainwants,saidhere at the munich security conference.
• 发言者 2 14:39
China's gas station, I would add,it's a gas station with with anarmythis means you have a you have a IoT ofinfluenceon ukraine. Do you see AA possibility now that there is more pressure and finally more pressure to finish this war that from from yourend,you couldmaybe do something on your side of thegas station,
• 发言者 2 15:11
and maybecutthe possibility of russia to supply gas to to your country or lower the price orStop some of the dual use goods that are coming there so thatthere's more pressure on russia to finally finish this war.
• 发言者 1 15:32
中国同俄罗斯，我们是两大邻国，有着漫长的边界。两国关系。过去经历过一番曲折的经历。之后我们双方吸取教训，我们建立了结盟不对抗，不针对第三方的那么睦邻友好关系，进而我们增进了我们的战略互信，建立了全面战略伙伴关系。中国同俄罗斯之间的交往是正常的，国与国之间的交往刚才提到中国可不可以不从俄罗斯买油气了？我想问一句，如果中国不从俄罗斯买，哪个国家能够提供如此巨量的油气来满足中国民众的需求呢？那是不可能的，也是不保险的。
• 发言者 1 16:24
因为常常有的国家把经贸问题政治化，当做打压中国的工具，我们不会允许出现这样的情况，我们要为我们的人民负责任。但是中国在对待地区热点问题上是有我们的立场的。我们历来主张一切争端和冲突都应该通过对话寻求政治解决。因为武力和制裁不可能真正和彻底的解决问题，乌克兰问题上同样如此。从这场危机爆发的第2天开始，就是2022年2月25号，中方就提出了对话协商解决。习近平主席提出的4点主张是中国立场的最权威的阐释，那就是各国的主权领土完整应该得到尊重，
• 发言者 1 17:25
联合国的宪章应该得到遵守。各国的合理安全关切应该得到重视。一切致力于和平的努力都应该得到支持。我们就是以此为遵循，在不断的推进我们的劝和促谈，哪怕呢有一点希望，我们就要做出我们的百倍的努力，我们派出的特使去各国斡旋。我们同巴西等南方国家发起了和平之友。那么中国的这些立场现在看随着时间的推移，应该说是公正的客观的。也是理性的务实的，体现了国际社会的最大的共识。任何冲突的终点都是谈判桌，历史最终一定是公正的。中方乐见一切。致力于和平的努力。包括这两天美国同俄罗斯达成的共识。
• 发言者 1 18:45
同时我们认为所有当事方包括利益攸关方，都应该适时的参与到这个和谈的进程当中。这场战事发生在欧洲大地上，欧洲更有必要为此发挥重要的作用，共同来解决好危机。的根源性的因素，共同来探讨欧洲的长治久安。找到大家都能够接受的。均衡有效可持续的，欧洲的安全的框架，谢谢。
• 发言者 2 19:37
We are we have run out of time, but I would at least very briefly ask you to give us a sneak preview of how you think the relationship between us and China will develop.
• 发言者 1 19:53
这是一个大家都关心的问题，我要在这里首先告诉大家的是中国的对美政策保持着连续性和稳定性，我们不会轻易的翻烙饼。这体现了作为大国的战略定力和国际信誉。我们的对美政策就是习近平主席提出的三原则，相互尊重，和平共处。合作共赢。中国和美国我们制度确实不一样，这是我们各自人民做出的选择。如果想改造或者颠覆对方的话，那是不切实际的。正确的态度就是相互尊重。这是中美交往的一个前提。和平共处。更是理所当然。中美两个大国总不能冲突起来吧，因为那将殃及整个世界，所以还是要开展对话，
• 发言者 1 20:58
加强交往，增进了解。建立信任。合作共赢，这是因为国际社会期待中美开展合作。全球性的挑战也需要中美携手来应对。当然这也是中美两个大国应当承担的国际责任。中方已经准备好了，我们愿意按照三原则同美方构建稳定健康可持续的双边关系，找到两个大国在这个星球上的正确相处之道。我们当然希望美方能够相向而行。但是如果美方不愿意，如果美方仍然还要对中国打压和遏制，那我们也别无选择，我们必将奉陪到底。我们必将坚定的维护中国的主权。中国的国家的尊严和我们的正当发展权利。必将坚决的回击。美方的单。单机和霸凌的这种行径。中国这样做也是为了维护国际的公平正义，
• 发言者 1 22:35
为了维护国际关系的基本准则，中国人从来不信邪，不怕鬼。新中国就是在战胜各种艰难险阻中发展。壮大起来的。中国有句古话叫做天行健。军事自强不息。中国还有一句话，说得很形象，那就是他强任他强，清风拂山岗。他横任他横明月照大江。任尔东西南北风。我自泰然处之。岿然不动。这几句话可能翻译起来。不容易，唉可能又会出来很多翻译的版本，大家可以相互切磋。也可以找deep seek来帮一帮忙。总之我们对这个世界的前途是充满信心的。同样我们对中美关系的未来也是充满信心的。中美两国只有一个我们共同努力的方向，
• 发言者 1 24:08
那就是刚才我反复谈到的相互尊重，和平共处，合作共赢，这也是国际社会最大的期待，谢谢。
• 发言者 2 24:30
very much.Also, for this proverb,喂see if we have chat gp or so, translating IT. But I thought the british, the english translation,喂got was pretty good. . Thank you for being. Yeah, I hope I sincerely hope. Also, you can usethe possibility ofmunich to meet withrepresentatives of the new us administration,
• 发言者 2 24:50
and IT would be very good that what you are,what you are also proposing. More talks and discussion on these issues withmaterialS here in munich. I wish you again. Good luck to you on your trip to new york and thank you for being such a goodguest here to the munich security conference.
• 发言者 2 25:12
Thank you for this all the best. .
"""
BASE_URL = os.getenv("AGENTFLOW_BASE_URL", "http://127.0.0.1:8888").rstrip("/")
URL = f"{BASE_URL}/api/agent/v1"
USER_ID = "1"

resp = requests.post(
    URL,
    json={
        "domain": "meeting",
        "task": "minutes",
        "texts": {
            "transcript": TRANSCRIPT,
            "keypoints": "",
            "notes": "",
        },
        "docs": [],
        "memory": False,
        "extra": {
            "time": "2026-09-08",
            "template": "media_briefing",
            "profile": "",
            "project": "",
            "subject": "",
            "style": "",
        },
    },
    headers={"X-Request-Id": uuid.uuid4().hex, "X-User-Id": USER_ID},
    timeout=300,
)
data = resp.json()

print("HTTP", resp.status_code)
print("code       :", data.get("code"))
print("request_id :", data.get("request_id"))
print("message    :", data.get("message"))
monitor = data.get("monitor") or {}
print("token      :", monitor.get("token_usage"), "| cache:", monitor.get("cache_hit"), "| cost:", monitor.get("cost_time"), "s")
d = data.get("data") or {}
print("file_name  :", d.get("file_name"))
print("text       :")
print(d.get("text"))
