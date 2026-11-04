#g++ -std=c++17 src/main.cpp src/core/*.cpp src/entities/*.cpp src/systems/*.cpp src/levels/*.cpp src/factories/*.cpp -o bomberman && ./bomberman
#for file in include/*/*.h src/*.cpp src/*/*.cpp; do echo -e "\n==================== $file ===================="; cat "$file"; done


g++ -O3 -Wall -shared -std=c++17 -fPIC \
-Iinclude \
$(python3 -m pybind11 --includes) \
src/bindings/bindings.cpp src/core/Board.cpp src/core/ConsoleInput.cpp \
src/core/ConsoleRenderer.cpp src/core/Game.cpp src/core/World.cpp \
src/entities/Entity.cpp src/entities/Player.cpp src/entities/Bomb.cpp \
src/entities/Flame.cpp src/entities/BreakableWall.cpp src/entities/DumbBot.cpp \
src/entities/PowerUp.cpp src/entities/BombPowerUp.cpp src/entities/LightningPowerUp.cpp \
src/entities/SpeedPowerUp.cpp src/entities/HammerPowerUp.cpp src/entities/RingPowerUp.cpp \
src/factories/PowerUpFactory.cpp src/levels/ClassicLevel.cpp \
src/systems/CollisionSystem.cpp src/systems/ExplosionSystem.cpp src/systems/SuddenDeathSystem.cpp \
-o bomberman_engine$(python3-config --extension-suffix)