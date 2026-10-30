# -*- coding: utf-8 -*-
"""随机奖池配置

- POOL：可抽到的物品ID列表（基岩版格式 minecraft:xxx），想增删奖励直接改这个列表
- NON_STACKABLE：不可堆叠物品（工具/武器/盔甲等），抽到时数量恒为1；其余物品随机 1~3 个
"""

import random

POOL = [
    # ---- 矿物 / 宝石 ----
    "minecraft:coal", "minecraft:charcoal", "minecraft:iron_ingot",
    "minecraft:copper_ingot", "minecraft:gold_ingot", "minecraft:redstone",
    "minecraft:lapis_lazuli", "minecraft:diamond", "minecraft:emerald",
    "minecraft:quartz", "minecraft:amethyst_shard", "minecraft:netherite_scrap",
    "minecraft:netherite_ingot", "minecraft:glowstone_dust", "minecraft:echo_shard",
    "minecraft:ancient_debris", "minecraft:nether_star",
    # ---- 食物 ----
    "minecraft:apple", "minecraft:golden_apple", "minecraft:enchanted_golden_apple",
    "minecraft:bread", "minecraft:cookie", "minecraft:cake", "minecraft:pumpkin_pie",
    "minecraft:cooked_beef", "minecraft:cooked_porkchop", "minecraft:cooked_chicken",
    "minecraft:cooked_mutton", "minecraft:cooked_rabbit", "minecraft:cooked_cod",
    "minecraft:cooked_salmon", "minecraft:carrot", "minecraft:golden_carrot",
    "minecraft:potato", "minecraft:baked_potato", "minecraft:beetroot",
    "minecraft:melon_slice", "minecraft:sweet_berries", "minecraft:glow_berries",
    "minecraft:chorus_fruit", "minecraft:honey_bottle", "minecraft:dried_kelp",
    "minecraft:milk_bucket",
    # ---- 种子 / 农作物 ----
    "minecraft:wheat_seeds", "minecraft:pumpkin_seeds", "minecraft:melon_seeds",
    "minecraft:beetroot_seeds", "minecraft:wheat", "minecraft:sugar_cane",
    "minecraft:sugar", "minecraft:cocoa_beans", "minecraft:nether_wart",
    "minecraft:egg", "minecraft:bamboo",
    # ---- 生物掉落 / 杂项 ----
    "minecraft:string", "minecraft:leather", "minecraft:feather", "minecraft:flint",
    "minecraft:gunpowder", "minecraft:slime_ball", "minecraft:ender_pearl",
    "minecraft:blaze_rod", "minecraft:blaze_powder", "minecraft:ghast_tear",
    "minecraft:magma_cream", "minecraft:phantom_membrane", "minecraft:rabbit_foot",
    "minecraft:rabbit_hide", "minecraft:ink_sac", "minecraft:glow_ink_sac",
    "minecraft:spider_eye", "minecraft:bone", "minecraft:bone_meal",
    "minecraft:rotten_flesh", "minecraft:shulker_shell", "minecraft:nautilus_shell",
    "minecraft:heart_of_the_sea", "minecraft:prismarine_shard",
    "minecraft:prismarine_crystals", "minecraft:dragon_breath",
    "minecraft:totem_of_undying", "minecraft:experience_bottle",
    # ---- 工具 / 武器 / 盔甲 ----
    "minecraft:iron_sword", "minecraft:iron_pickaxe", "minecraft:iron_axe",
    "minecraft:iron_shovel", "minecraft:iron_hoe",
    "minecraft:diamond_sword", "minecraft:diamond_pickaxe", "minecraft:diamond_axe",
    "minecraft:diamond_shovel", "minecraft:diamond_hoe",
    "minecraft:golden_sword", "minecraft:golden_pickaxe",
    "minecraft:bow", "minecraft:crossbow", "minecraft:arrow", "minecraft:shield",
    "minecraft:fishing_rod", "minecraft:shears", "minecraft:flint_and_steel",
    "minecraft:iron_helmet", "minecraft:iron_chestplate", "minecraft:iron_leggings",
    "minecraft:iron_boots", "minecraft:diamond_helmet", "minecraft:diamond_chestplate",
    "minecraft:diamond_leggings", "minecraft:diamond_boots", "minecraft:turtle_helmet",
    "minecraft:elytra", "minecraft:trident",
    # ---- 方块 / 其他 ----
    "minecraft:cobblestone", "minecraft:stone", "minecraft:dirt", "minecraft:sand",
    "minecraft:gravel", "minecraft:oak_log", "minecraft:birch_log",
    "minecraft:spruce_log", "minecraft:oak_planks", "minecraft:glass",
    "minecraft:obsidian", "minecraft:crying_obsidian", "minecraft:tnt",
    "minecraft:book", "minecraft:paper", "minecraft:compass", "minecraft:clock",
    "minecraft:name_tag", "minecraft:saddle", "minecraft:iron_horse_armor",
    "minecraft:golden_horse_armor", "minecraft:lead", "minecraft:torch",
    "minecraft:lantern", "minecraft:chest", "minecraft:crafting_table",
    "minecraft:furnace", "minecraft:bucket", "minecraft:water_bucket",
    "minecraft:lava_bucket", "minecraft:ender_chest", "minecraft:shulker_box",
    "minecraft:respawn_anchor", "minecraft:conduit", "minecraft:sea_lantern",
    "minecraft:glass_bottle", "minecraft:fermented_spider_eye",
    "minecraft:glistering_melon_slice", "minecraft:rabbit_stew",
]

NON_STACKABLE = {
    "minecraft:iron_sword", "minecraft:iron_pickaxe", "minecraft:iron_axe",
    "minecraft:iron_shovel", "minecraft:iron_hoe",
    "minecraft:diamond_sword", "minecraft:diamond_pickaxe", "minecraft:diamond_axe",
    "minecraft:diamond_shovel", "minecraft:diamond_hoe",
    "minecraft:golden_sword", "minecraft:golden_pickaxe",
    "minecraft:bow", "minecraft:crossbow", "minecraft:shield",
    "minecraft:fishing_rod", "minecraft:shears", "minecraft:flint_and_steel",
    "minecraft:iron_helmet", "minecraft:iron_chestplate", "minecraft:iron_leggings",
    "minecraft:iron_boots", "minecraft:diamond_helmet", "minecraft:diamond_chestplate",
    "minecraft:diamond_leggings", "minecraft:diamond_boots", "minecraft:turtle_helmet",
    "minecraft:elytra", "minecraft:trident",
    "minecraft:saddle", "minecraft:iron_horse_armor", "minecraft:golden_horse_armor",
    "minecraft:shulker_box",
}


def RollItem():
    """随机抽取一个物品，返回可直接用于 SpawnItemToPlayerInv 的物品字典"""
    name = random.choice(POOL)
    count = 1 if name in NON_STACKABLE else random.randint(1, 3)
    return {"newItemName": name, "newAuxValue": 0, "count": count}
