#include <pybind11/pybind11.h>
#include <pybind11/stl.h> // 
#include "../../include/core/Game.h"
#include "../../include/levels/ClassicLevel.h"

namespace py = pybind11;

PYBIND11_MODULE(bomberman_engine, m) {
    m.doc() = "C++ Bomberman Engine bound to Python";

    py::enum_<Command>(m, "Command")
        .value("NONE", Command::NONE)
        .value("UP", Command::UP)
        .value("DOWN", Command::DOWN)
        .value("LEFT", Command::LEFT)
        .value("RIGHT", Command::RIGHT)
        .value("PLACE_BOMB", Command::PLACE_BOMB)
        .export_values();

    py::class_<StepResult>(m, "StepResult")
        .def_readonly("isDone", &StepResult::isDone)
        .def_readonly("reward", &StepResult::reward);

    py::class_<ILevel>(m, "ILevel"); 
    py::class_<ClassicLevel, ILevel>(m, "ClassicLevel")
        .def(py::init<int, int, int>()); 

    py::class_<Game>(m, "Game")
        .def(py::init<int, int>()) 
        .def("reset", &Game::reset)
        .def("step", &Game::step)
        .def("getState", &Game::getState)
        .def("isGameOver", &Game::isGameOver)
        .def("getWinnerId", &Game::getWinnerId);
}
