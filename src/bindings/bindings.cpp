#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <pybind11/numpy.h>
#include <algorithm>
#include <cstdlib>
#include <ctime>
#include "../../include/core/Game.h"
#include "../../include/levels/ClassicLevel.h"
#include "../../include/factories/PowerUpFactory.h"
#include "../../include/entities/DumbBot.h"

namespace py = pybind11;

PYBIND11_MODULE(bomberman_engine, m) {
    m.doc() = "C++ Bomberman Engine bound to Python";

    std::srand(static_cast<unsigned int>(std::time(nullptr)));

    m.def("seed_rng", [](unsigned int seed) {
        std::srand(seed);
    }, "Seeds the C++ rand() generator for reproducible level generation");

    m.def("set_powerup_drop_chance", &PowerUpFactory::setDropChancePercent, py::arg("percent"),
          "Sets the percentage chance (0-100) that a destroyed breakable wall drops a power-up");
    m.def("get_powerup_drop_chance", &PowerUpFactory::getDropChancePercent,
          "Gets the percentage chance (0-100) that a destroyed breakable wall drops a power-up");

    m.def("set_bot_sd_caution_percent", &DumbBot::setSuddenDeathCautionPercent, py::arg("percent"),
          "Sets the base caution probability (0-100) for DumbBot Sudden Death awareness");
    m.def("get_bot_sd_caution_percent", &DumbBot::getSuddenDeathCautionPercent,
          "Gets the base caution probability (0-100) for DumbBot Sudden Death awareness");

    py::enum_<Command>(m, "Command")
        .value("NONE", Command::NONE)
        .value("UP", Command::UP)
        .value("DOWN", Command::DOWN)
        .value("LEFT", Command::LEFT)
        .value("RIGHT", Command::RIGHT)
        .value("PLACE_BOMB", Command::PLACE_BOMB)
        .export_values();

    py::class_<PlayerCommand>(m, "PlayerCommand")
        .def(py::init<int, Command>(), py::arg("playerId"), py::arg("command"))
        .def_readwrite("playerId", &PlayerCommand::playerId)
        .def_readwrite("command", &PlayerCommand::command);

    py::class_<StepResult>(m, "StepResult")
        .def_readonly("isDone", &StepResult::isDone)
        .def_readonly("reward", &StepResult::reward)
        .def_readonly("wallsDestroyed", &StepResult::wallsDestroyed)
        .def_readonly("enemiesHit", &StepResult::enemiesHit)
        .def_readonly("enemiesKilled", &StepResult::enemiesKilled)
        .def_readonly("powerUpsCollected", &StepResult::powerUpsCollected)
        .def_readonly("livesLost", &StepResult::livesLost)
        .def_readonly("moved", &StepResult::moved)
        .def_readonly("bombPlaced", &StepResult::bombPlaced)
        .def_readonly("bombPushed", &StepResult::bombPushed)
        .def_readonly("won", &StepResult::won)
        .def_readonly("died", &StepResult::died);

    py::class_<PlayerInfo>(m, "PlayerInfo")
        .def_readonly("id", &PlayerInfo::id)
        .def_readonly("x", &PlayerInfo::x)
        .def_readonly("y", &PlayerInfo::y)
        .def_readonly("lives", &PlayerInfo::lives)
        .def_readonly("maxBombs", &PlayerInfo::maxBombs)
        .def_readonly("availBombs", &PlayerInfo::availBombs)
        .def_readonly("bombRadius", &PlayerInfo::bombRadius)
        .def_readonly("speedLevel", &PlayerInfo::speedLevel)
        .def_readonly("cooldown", &PlayerInfo::cooldown)
        .def_readonly("moveCooldownMax", &PlayerInfo::moveCooldownMax)
        .def_readonly("invincibilityTimer", &PlayerInfo::invincibilityTimer)
        .def_readonly("facingDx", &PlayerInfo::facingDx)
        .def_readonly("facingDy", &PlayerInfo::facingDy)
        .def_readonly("hasHammer", &PlayerInfo::hasHammer)
        .def_readonly("hasRing", &PlayerInfo::hasRing)
        .def_readonly("isBot", &PlayerInfo::isBot)
        .def_readonly("isAlive", &PlayerInfo::isAlive);

    py::class_<BombInfo>(m, "BombInfo")
        .def_readonly("x", &BombInfo::x)
        .def_readonly("y", &BombInfo::y)
        .def_readonly("timer", &BombInfo::timer)
        .def_readonly("radius", &BombInfo::radius)
        .def_readonly("ownerId", &BombInfo::ownerId)
        .def_readonly("creditOwnerId", &BombInfo::creditOwnerId)
        .def_readonly("isSliding", &BombInfo::isSliding)
        .def_readonly("slideDx", &BombInfo::slideDx)
        .def_readonly("slideDy", &BombInfo::slideDy)
        .def_readonly("slideCooldown", &BombInfo::slideCooldown)
        .def_readonly("slideCooldownMax", &BombInfo::slideCooldownMax);

    py::class_<PowerUpInfo>(m, "PowerUpInfo")
        .def_readonly("x", &PowerUpInfo::x)
        .def_readonly("y", &PowerUpInfo::y)
        .def_readonly("type", &PowerUpInfo::type);

    py::class_<FlameInfo>(m, "FlameInfo")
        .def_readonly("x", &FlameInfo::x)
        .def_readonly("y", &FlameInfo::y)
        .def_readonly("timer", &FlameInfo::timer)
        .def_readonly("ownerId", &FlameInfo::ownerId)
        .def_readonly("creditOwnerId", &FlameInfo::creditOwnerId);

    py::class_<ILevel>(m, "ILevel");
    py::class_<ClassicLevel, ILevel>(m, "ClassicLevel")
        .def(py::init<int, int, int, int>(),
             py::arg("numPlayers"),
             py::arg("boardWidth"),
             py::arg("boardHeight"),
             py::arg("wallDensityPercent") = 65);

    py::class_<Game>(m, "Game")
        .def(py::init<int, int>())
        .def("reset", &Game::reset)
        .def("step", &Game::step,
             py::arg("playerId"),
             py::arg("action"),
             py::arg("extraCommands") = std::vector<PlayerCommand>{})
        .def("update", py::overload_cast<Command>(&Game::update), py::arg("command") = Command::NONE)
        .def("updateCommands", py::overload_cast<const std::vector<PlayerCommand>&>(&Game::update), py::arg("commands"))
        .def("getState", [](const Game& self, int playerId) {
            const int width = self.getWorld().getBoard().getWidth();
            const int height = self.getWorld().getBoard().getHeight();
            constexpr int channels = 17;
            py::array_t<float> result({channels, height, width});
            float* ptr = static_cast<float*>(result.request().ptr);
            std::fill(ptr, ptr + (channels * height * width), 0.0f);
            self.fillState(playerId, ptr);
            return result;
        }, py::arg("playerId"))
        .def("getBoardGrid", &Game::getBoardGrid)
        .def("getPlayerInfo", &Game::getPlayerInfo)
        .def("getBombs", &Game::getBombs)
        .def("getPowerUps", &Game::getPowerUps)
        .def("getFlames", &Game::getFlames)
        .def("clearBoard", &Game::clearBoard)
        .def("setSolidWall", &Game::setSolidWall)
        .def("addPlayer", &Game::addPlayer, py::arg("x"), py::arg("y"), py::arg("id"), py::arg("isBot") = false)
        .def("addBreakableWall", &Game::addBreakableWall)
        .def("addBomb", &Game::addBomb)
        .def("addPowerUp", &Game::addPowerUp)
        .def("givePlayerPowerUp", &Game::givePlayerPowerUp)
        .def("isGameOver", &Game::isGameOver)
        .def("getWinnerId", &Game::getWinnerId)
        .def("getSuddenDeathTimer", &Game::getSuddenDeathTimer)
        .def("setSuddenDeathTimer", &Game::setSuddenDeathTimer)
        .def("isSuddenDeathActive", &Game::isSuddenDeathActive);
}
