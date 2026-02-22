"""Static constants: known plugins, stage list, UI colors."""
from src.models.plugin import KnownPluginInfo

# Known Skyline plugins with descriptions
KNOWN_PLUGINS = {
    "libarcropolis.nro": KnownPluginInfo(
        filename="libarcropolis.nro",
        display_name="ARCropolis",
        description="Core mod loader for SSBU. Enables file replacement mods. Required for most mods to work.",
        url="https://github.com/Raytwo/ARCropolis",
        required=True,
    ),
    "libparam_hook.nro": KnownPluginInfo(
        filename="libparam_hook.nro",
        display_name="Param Hook",
        description="Hooks parameter file loading for dynamic param modification at runtime.",
    ),
    "libacmd_hook.nro": KnownPluginInfo(
        filename="libacmd_hook.nro",
        display_name="ACMD Hook",
        description="Hooks the Animation Command (ACMD) system for custom movesets and attacks.",
    ),
    "libnro_hook.nro": KnownPluginInfo(
        filename="libnro_hook.nro",
        display_name="NRO Hook",
        description="Enables loading additional NRO plugins at runtime.",
    ),
    "libtraining_modpack.nro": KnownPluginInfo(
        filename="libtraining_modpack.nro",
        display_name="Training Modpack",
        description="Enhanced training mode with frame data, input display, and advanced options.",
        url="https://github.com/jugeeya/UltimateTrainingModpack",
    ),
    "libskyline_web.nro": KnownPluginInfo(
        filename="libskyline_web.nro",
        display_name="Skyline Web",
        description="Web-based plugin manager accessible from the console's browser.",
    ),
    "libhdr.nro": KnownPluginInfo(
        filename="libhdr.nro",
        display_name="HDR (HewDraw Remix)",
        description="Major gameplay overhaul mod with rebalanced fighters and mechanics.",
        url="https://github.com/HDR-Development/HewDraw-Remix",
    ),
    "libsmashline_plugin.nro": KnownPluginInfo(
        filename="libsmashline_plugin.nro",
        display_name="Smashline",
        description="Framework for custom fighter movesets. Enables ACMD script replacement and status script changes.",
    ),
    "libparam_config.nro": KnownPluginInfo(
        filename="libparam_config.nro",
        display_name="Param Config",
        description="Allows per-mod parameter file configuration. Required by many moveset mods for custom fighter params.",
    ),
    "libstage_config.nro": KnownPluginInfo(
        filename="libstage_config.nro",
        display_name="Stage Config",
        description="Stage-specific configuration plugin. Enables custom stage parameters and modded stage setups.",
    ),
    "libcss_preserve.nro": KnownPluginInfo(
        filename="libcss_preserve.nro",
        display_name="CSS Preserve",
        description="Preserves Character Select Screen cursor positions and selections between matches.",
    ),
    "liblatency_slider_de.nro": KnownPluginInfo(
        filename="liblatency_slider_de.nro",
        display_name="Latency Slider",
        description="Adds a latency/input delay slider for fine-tuning online play responsiveness.",
    ),
    "libone_slot_eff.nro": KnownPluginInfo(
        filename="libone_slot_eff.nro",
        display_name="One Slot Effect",
        description="Allows visual effects to be loaded per costume slot. Enables unique effects for each alt costume.",
    ),
    "libresults_screen.nro": KnownPluginInfo(
        filename="libresults_screen.nro",
        display_name="Results Screen",
        description="Customizes the results/victory screen. Shows correct character names and portraits for custom fighters.",
    ),
    "libthe_csk_collection.nro": KnownPluginInfo(
        filename="libthe_csk_collection.nro",
        display_name="The CSK Collection",
        description="Collection of game tweaks and quality-of-life improvements for competitive and casual play.",
    ),
    "libtesting.nro": KnownPluginInfo(
        filename="libtesting.nro",
        display_name="Testing Plugin",
        description="Development/testing plugin for debugging and testing mod functionality.",
    ),
}

# SSBU vanilla stages (stage_id -> display name)
VANILLA_STAGES = {
    "ui_stage_id_battlefield": "Battlefield",
    "ui_stage_id_battlefield_s": "Small Battlefield",
    "ui_stage_id_end": "Final Destination",
    "ui_stage_id_mario_castle64": "Peach's Castle",
    "ui_stage_id_dk_jungle": "Kongo Jungle",
    "ui_stage_id_zelda_hyrule": "Hyrule Castle",
    "ui_stage_id_yoshi_story": "Super Happy Tree",
    "ui_stage_id_kirby_pupupu64": "Dream Land",
    "ui_stage_id_poke_yamabuki": "Saffron City",
    "ui_stage_id_mario_past64": "Mushroom Kingdom",
    "ui_stage_id_mario_rainbow": "Rainbow Cruise",
    "ui_stage_id_dk_waterfall": "Kongo Falls",
    "ui_stage_id_zelda_greatbay": "Great Bay",
    "ui_stage_id_zelda_temple": "Temple",
    "ui_stage_id_metroid_brinstar": "Brinstar",
    "ui_stage_id_yoshi_yoster": "Yoshi's Island (Melee)",
    "ui_stage_id_fzero_bigblue": "Big Blue",
    "ui_stage_id_mother_onett": "Onett",
    "ui_stage_id_mario_dolpic": "Delfino Plaza",
    "ui_stage_id_mario_pastusa": "Mushroom Kingdom II",
    "ui_stage_id_metroid_kraid": "Brinstar Depths",
    "ui_stage_id_yoshi_cartboard": "Yoshi's Island",
    "ui_stage_id_fzero_mutecity3ds": "Mute City SNES",
    "ui_stage_id_kirby_fountain": "Fountain of Dreams",
    "ui_stage_id_mario_pastx": "Mushroomy Kingdom",
    "ui_stage_id_fw_shrine": "Garden of Hope",
    "ui_stage_id_zelda_oldin": "Bridge of Eldin",
    "ui_stage_id_animal_village": "Smashville",
    "ui_stage_id_animal_island": "Tortimer Island",
    "ui_stage_id_animal_city": "Town and City",
    "ui_stage_id_poke_stadium": "Pokemon Stadium",
    "ui_stage_id_poke_stadium2": "Pokemon Stadium 2",
    "ui_stage_id_poke_tengam": "Spear Pillar",
    "ui_stage_id_poke_unova": "Unova Pokemon League",
    "ui_stage_id_poke_kalos": "Kalos Pokemon League",
    "ui_stage_id_mario_newndonk": "New Donk City Hall",
    "ui_stage_id_mario_3dland": "3D Land",
    "ui_stage_id_mario_paper": "Paper Mario",
    "ui_stage_id_mario_uworld": "Mushroom Kingdom U",
    "ui_stage_id_mario_odyssey": "New Donk City",
    "ui_stage_id_fe_siege": "Castle Siege",
    "ui_stage_id_fe_arena": "Arena Ferox",
    "ui_stage_id_fe_colosseum": "Coliseum",
    "ui_stage_id_zelda_skyward": "Skyloft",
    "ui_stage_id_zelda_gerudo": "Gerudo Valley",
    "ui_stage_id_zelda_tower": "Great Plateau Tower",
    "ui_stage_id_kirby_gameboy": "Dream Land GB",
    "ui_stage_id_kirby_halberd": "Halberd",
    "ui_stage_id_metroid_norfair": "Norfair",
    "ui_stage_id_metroid_orpheon": "Frigate Orpheon",
    "ui_stage_id_sf_suzaku": "Suzaku Castle",
    "ui_stage_id_mother_magicant": "Magicant",
    "ui_stage_id_mother_newpork": "New Pork City",
    "ui_stage_id_xeno_gaur": "Gaur Plain",
    "ui_stage_id_sonic_greenhill": "Green Hill Zone",
    "ui_stage_id_sonic_windyhill": "Windy Hill Zone",
    "ui_stage_id_fzero_porttown": "Port Town Aero Dive",
    "ui_stage_id_iceclimber_summit": "Summit",
    "ui_stage_id_wario_gamer": "Gamer",
    "ui_stage_id_wario_madein": "WarioWare, Inc.",
    "ui_stage_id_punchoutsb": "Boxing Ring",
    "ui_stage_id_pac_land": "PAC-LAND",
    "ui_stage_id_mg_shadowmoses": "Shadow Moses Island",
    "ui_stage_id_lylat_corneria": "Corneria",
    "ui_stage_id_lylat_venom": "Venom",
    "ui_stage_id_lylat_sector": "Lylat Cruise",
    "ui_stage_id_dk_returns": "Jungle Japes",
    "ui_stage_id_dk_lodge": "75 m",
    "ui_stage_id_mario_maker": "Super Mario Maker",
    "ui_stage_id_pikmin_planet": "Distant Planet",
    "ui_stage_id_wuhu_island": "Wuhu Island",
    "ui_stage_id_tomodachi": "Tomodachi Life",
    "ui_stage_id_miiverse": "Miiverse",
    "ui_stage_id_nintendogs": "Living Room",
    "ui_stage_id_wiifit_gym": "Wii Fit Studio",
    "ui_stage_id_duckhunt_village": "Duck Hunt",
    "ui_stage_id_pilotwings": "Pilotwings",
    "ui_stage_id_wreckingcrew": "Wrecking Crew",
    "ui_stage_id_balloonfight": "Balloon Fight",
    "ui_stage_id_flatzone_x": "Flat Zone X",
    "ui_stage_id_electroplankton": "Hanenbow",
    "ui_stage_id_pictochat2": "PictoChat 2",
    "ui_stage_id_kaclash_castle": "Find Mii",
    "ui_stage_id_splatoon_stage": "Moray Towers",
    "ui_stage_id_dracula_castle": "Dracula's Castle",
    "ui_stage_id_jack_mementoes": "Mementos",
    "ui_stage_id_brave_altar": "Yggdrasil's Altar",
    "ui_stage_id_dolly_stadium": "King of Fighters Stadium",
    "ui_stage_id_tantan_spring": "Spring Stadium",
    "ui_stage_id_trail_castle": "Northern Cave",
    "ui_stage_id_xeno_alst": "Cloud Sea of Alrest",
    "ui_stage_id_demon_dojo": "Mishima Dojo",
    "ui_stage_id_minecraft_world": "Minecraft World",
    "ui_stage_id_battlefield_l": "Big Battlefield",
    "ui_stage_id_training": "Training",
    "ui_stage_id_homerun_stadium": "Home-Run Stadium",
    "ui_stage_id_battle_skyworld": "Skyworld",
    "ui_stage_id_sp_edit": "Custom Stage",
    "ui_stage_id_ff_midgar": "Midgar",
    "ui_stage_id_bayo_clock": "Umbra Clock Tower",
    "ui_stage_id_stranger_dungeon": "Hollow Bastion",
}

# File types that can cause conflicts
CONFLICT_EXTENSIONS = {".xmsbt", ".msbt", ".prc", ".stprm", ".stdat"}
MERGEABLE_EXTENSIONS = {".xmsbt"}

# Tournament-legal competitive stages (commonly used in official rulesets)
COMPETITIVE_STAGES = {
    "ui_stage_id_battlefield",
    "ui_stage_id_battlefield_s",
    "ui_stage_id_end",
    "ui_stage_id_animal_village",    # Smashville
    "ui_stage_id_animal_city",       # Town and City
    "ui_stage_id_poke_stadium2",     # Pokemon Stadium 2
    "ui_stage_id_poke_kalos",        # Kalos Pokemon League
    "ui_stage_id_stranger_dungeon",  # Hollow Bastion
    "ui_stage_id_trail_castle",      # Northern Cave
    "ui_stage_id_yoshi_story",       # Super Happy Tree (Yoshi's Story)
}

# File categories based on path patterns
FILE_CATEGORIES = {
    "character": ["fighter/", "ui/replace/chara/", "sound/bank/narration/"],
    "music": ["sound/bgm/", "stream/"],
    "stage": ["stage/", "ui/replace/stage/"],
    "ui": ["ui/", "param/"],
    "effect": ["effect/"],
}

# UI constants
SIDEBAR_WIDTH = 200
SIDEBAR_BG = "#1a1a2e"
SIDEBAR_HOVER = "#16213e"
SIDEBAR_ACTIVE = "#0f3460"
ACCENT_COLOR = "#1f538d"
SUCCESS_COLOR = "#2fa572"
WARNING_COLOR = "#b08a2a"
DANGER_COLOR = "#b02a2a"
