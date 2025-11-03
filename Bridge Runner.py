from ursina import *
import random, math, time

app = Ursina()
window.exit_button.visible = False

# -------------------- ค่าพื้นฐานฉาก --------------------
START_SIZE   = 40
GOAL_SIZE    = 20
GAP_START_Z  = START_SIZE/2          # 20
GAP_END_Z    = 70
GOAL_Z       = GAP_END_Z + GOAL_SIZE/2

SPAWN_INTERVAL = 3.5
PLAYER_LANE_X  = -2
BOT_LANE_X     =  2
BLOCK_Y        = 0.5
STEP_RISE      = 0.03
BUMP_COOLDOWN  = 0.8
BUMP_PUSH      = 1.0
BUMP_DROP_MAX  = 5

# -------------------- คลาสผู้เล่น/ตัววิ่ง --------------------
class Runner(Entity):
    def __init__(self, lane_x, color_main, **kwargs):
        super().__init__(model='cube', origin_y=-0.5, collider='box',
                         scale=(1,2,1), color=color_main, **kwargs)
        self.speed = 6
        self.jump_force = 7.5
        self.gravity = 22
        self.vel_y = 0
        self.inventory = 0
        self.lane_x = lane_x
        self.color_main = color_main
        self.next_bridge_z = int(GAP_START_Z + 1)
        self.stack_blocks = []
        self.safe_z = None   # ตำแหน่ง z ล่าสุดของสะพาน (กันตกแมพ)

    def on_ground(self):
        return raycast(self.world_position + Vec3(0,0.1,0), Vec3(0,-1,0),
                       distance=0.25, ignore=[self]).hit

    def move_input(self):
        move = Vec3(0,0,0)
        if held_keys['w']: move.z += 1
        if held_keys['s']: move.z -= 1
        if held_keys['a']: move.x -= 1
        if held_keys['d']: move.x += 1
        if move.length(): move = move.normalized()
        return move

    def physics_update(self, move_vec):
        if move_vec.length() > 0:
            self.position += move_vec * self.speed * time.dt
            self.rotation_y = math.degrees(math.atan2(move_vec.x, move_vec.z))

        if self.on_ground():
            if held_keys['space']:
                self.vel_y = self.jump_force
            else:
                self.vel_y = max(0, self.vel_y)
        else:
            self.vel_y -= self.gravity * time.dt
        self.y += self.vel_y * time.dt

        # ดูดเข้าเลนตรง
        if GAP_START_Z - 0.01 <= self.z <= GAP_END_Z + 0.01:
            self.x = lerp(self.x, self.lane_x, min(1, time.dt*8))

    def _update_stack_visual(self):
        for e in self.stack_blocks: destroy(e)
        self.stack_blocks.clear()
        for i in range(self.inventory):
            e = Entity(parent=self, model='cube', color=self.color_main,
                       scale=Vec3(0.8, 0.25, 0.8),
                       position=Vec3(0, 0.6 + i*0.23, -0.35))
            self.stack_blocks.append(e)

    def add_block(self, n=1):
        self.inventory += n
        self._update_stack_visual()

    def consume_block(self, n=1):
        self.inventory = max(0, self.inventory - n)
        self._update_stack_visual()

# -------------------- คลาสบอท --------------------
class Bot(Runner):
    def __init__(self, lane_x, color_main, **kwargs):
        super().__init__(lane_x=lane_x, color_main=color_main, **kwargs)
        self.speed = 5.2

    def ai_move(self, level):
        if self.z <= GAP_START_Z - 0.2:
            target = None
            colored = [b for b in level.collectables if b.color == self.color_main]
            if self.inventory < 6 and colored:
                target = min(colored, key=lambda b:
                             distance_2d(Vec2(self.x, self.z), Vec2(b.x, b.z)))
            if not target:
                target = Entity(position=Vec3(self.lane_x, 0.5, GAP_START_Z-0.5))
            dir_vec = (target.position - self.position)
            dir_vec.y = 0
            if dir_vec.length() > 0:
                dir_vec = dir_vec.normalized()
            return dir_vec

        target = Entity(position=Vec3(self.lane_x, 0.5, GOAL_Z))
        dir_vec = (target.position - self.position)
        dir_vec.y = 0
        if dir_vec.length() > 0:
            dir_vec = dir_vec.normalized()
        return dir_vec

# -------------------- เลเวลหลัก --------------------
class BridgeRaceLevel(Entity):
    def __init__(self):
        super().__init__()
        Sky()

        # เกาะเริ่ม
        self.start_island = Entity(model='plane', scale=(START_SIZE,1,START_SIZE),
                                   texture='white_cube', texture_scale=(START_SIZE,START_SIZE),
                                   color=color.lime.tint(-.25), collider='box', position=(0,0,0))

        # เกาะเส้นชัย
        self.goal_island = Entity(model='plane', scale=(GOAL_SIZE,1,GOAL_SIZE),
                                  color=color.green, collider='box', position=(0,0,GOAL_Z))
        self.goal_flag = Entity(model='cube', color=color.gold,
                                scale=(2,4,2), position=(0,2,GOAL_Z))

        # ผู้เล่น & บอท
        self.player = Runner(lane_x=PLAYER_LANE_X, color_main=color.azure,
                             position=Vec3(PLAYER_LANE_X,1,-START_SIZE/4))
        self.bot = Bot(lane_x=BOT_LANE_X, color_main=color.red,
                       position=Vec3(BOT_LANE_X,1,-START_SIZE/4))

        # กล้อง
        camera.fov = 60
        camera.position = Vec3(0, 40, -55)
        camera.rotation_x = 30

        # เก็บของ / สะพาน
        self.collectables = []
        for _ in range(14):
            self.spawn_block()
        invoke(self.spawn_block, delay=SPAWN_INTERVAL)
        self.player_bridge = []
        self.bot_bridge = []

        # UI
        self.player_text = Text(text='You: 0', position=Vec2(-0.47,0.45))
        self.bot_text    = Text(text='Bot: 0', position=Vec2( 0.33,0.45))
        self.win_text = None
        self._last_bump_time = 0.0

    def spawn_block(self):
        color_choice = random.choice([color.azure, color.red])
        x = random.randint(-int(START_SIZE/2)+1, int(START_SIZE/2)-1)
        z = random.randint(-int(START_SIZE/2)+1, int(START_SIZE/2)-1)
        b = Entity(model='cube', color=color_choice, scale=1,
                   position=(x,BLOCK_Y,z), collider='box')
        self.collectables.append(b)
        invoke(self.spawn_block, delay=SPAWN_INTERVAL)

    def try_pickup_blocks(self, runner: Runner):
        for block in list(self.collectables):
            if block.color != runner.color_main:
                continue
            if distance(runner.position, block.position) < 1.4 and runner.z <= GAP_START_Z + 0.01:
                self.collectables.remove(block)
                destroy(block)
                runner.add_block(1)
                break

    # ✅ เริ่มปูสะพานใกล้ขึ้น ไม่ต้องกระโดด
    def try_place_bridge_step(self, runner: Runner, bridge_list: list):
        BRIDGE_START_ZONE = GAP_START_Z - 1.0  # เริ่มปูก่อนถึงขอบ 1 หน่วย

        if not (BRIDGE_START_ZONE <= runner.z <= GAP_END_Z):
            return

        hit = raycast(runner.world_position + Vec3(0,0.1,0), Vec3(0,-1,0), distance=1.2)
        under_air = not hit.hit

        # ถ้ายังมีบล็อก → ปูสะพานล่วงหน้า
        if runner.inventory > 0:
            if under_air or runner.z >= runner.next_bridge_z:
                step_index = int(runner.next_bridge_z - BRIDGE_START_ZONE)
                piece_y = BLOCK_Y + step_index * STEP_RISE
                place_pos = Vec3(runner.lane_x, piece_y, float(runner.next_bridge_z))

                already_exist = any(
                    abs(p.position.x - place_pos.x) < 0.1 and abs(p.position.z - place_pos.z) < 0.1
                    for p in bridge_list
                )

                if not already_exist:
                    piece = Entity(model='cube', color=runner.color_main.tint(-.15),
                                   scale=(1,0.2,1), position=place_pos, collider='box')
                    bridge_list.append(piece)
                    runner.consume_block(1)
                    runner.safe_z = place_pos.z
                runner.next_bridge_z += 1

        # ถ้าบล็อกหมด → หยุดที่แผ่นสุดท้าย
        else:
            if under_air and runner.safe_z is not None:
                last_piece = None
                if bridge_list:
                    last_piece = max(bridge_list, key=lambda p: p.position.z)
                if last_piece:
                    runner.position = Vec3(runner.lane_x, last_piece.y + 1, last_piece.z)
                    runner.vel_y = 0

    def handle_bump(self):
        now = time.time()
        if now - self._last_bump_time < BUMP_COOLDOWN:
            return

        p = self.player
        b = self.bot
        if distance(p.position, b.position) > 1.2:
            return

        if p.inventory == b.inventory:
            return
        winner, loser = (p, b) if p.inventory > b.inventory else (b, p)
        drop_n = min(BUMP_DROP_MAX, max(1, winner.inventory - loser.inventory))
        drop_n = min(drop_n, loser.inventory)
        if drop_n <= 0:
            return

        on_ground_area = (loser.z <= GAP_START_Z + 0.05) or (loser.z >= GAP_END_Z - 0.05)
        if on_ground_area:
            for _ in range(drop_n):
                dx = random.uniform(-1.0, 1.0)
                dz = random.uniform(-1.0, 1.0)
                drop = Entity(model='cube', color=loser.color_main, scale=1,
                              position=Vec3(loser.x + dx, BLOCK_Y, loser.z + dz), collider='box')
                self.collectables.append(drop)
        loser.consume_block(drop_n)
        push_dir = (loser.position - winner.position)
        push_dir.y = 0
        if push_dir.length() > 0:
            push_dir = push_dir.normalized()
            loser.position += push_dir * BUMP_PUSH
        self._last_bump_time = now

    def reset_if_fall(self, runner: Runner):
        if runner.y < -5:
            runner.position = Vec3(runner.lane_x, 1, -START_SIZE/4)
            runner.vel_y = 0

    def update(self):
        # Player
        p_move = self.player.move_input()
        self.player.physics_update(p_move)
        self.try_pickup_blocks(self.player)
        self.try_place_bridge_step(self.player, self.player_bridge)
        self.reset_if_fall(self.player)

        # Bot
        b_move = self.bot.ai_move(self)
        self.bot.physics_update(b_move)
        self.try_pickup_blocks(self.bot)
        self.try_place_bridge_step(self.bot, self.bot_bridge)
        self.reset_if_fall(self.bot)

        # ชนกัน
        self.handle_bump()

        # UI
        self.player_text.text = f'You: {self.player.inventory}'
        self.bot_text.text = f'Bot: {self.bot.inventory}'

        # ชนะ
        if not self.win_text:
            if distance(self.player.position, self.goal_island.position) < GOAL_SIZE/2:
                self.win_text = Text('YOU WIN!', origin=(0,0), scale=3, color=color.gold)
            elif distance(self.bot.position, self.goal_island.position) < GOAL_SIZE/2:
                self.win_text = Text('BOT WINS!', origin=(0,0), scale=3, color=color.red)

# -------------------- เริ่มเกม --------------------
level = BridgeRaceLevel()
app.run()