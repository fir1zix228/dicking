#include <cfloat>
#include <iostream>
using namespace std;

int main() 
{
    setlocale(LC_ALL, "Rus");
    char op;
    double a, b, res;


    cout << "Введите действие (+, -, *, /): ";
    cin >> op;
    cout << "Введите два числа: ";
    cin >> a >> b;
    switch (op) {
    case '+':
        res = a + b;
        break;

    case '-':
        res = a - b;
        break;
    case '*':
        res = a * b;
        break;
    case '/':
        res = a / b;
        break;
    default:
        cout << "Ошибка! Оператор не правильный";
        res = -DBL_MAX;
    }
    if (res != -DBL_MAX)
        cout << "Результат: " << res;
    return 0;
}

