def soma(a, b):
    return a + b

def subtracao(a, b):
    return a - b

def multiplicacao(a, b):
    return a * b

def divisao(a, b):
    if b == 0:
        raise ValueError("Divisão por zero não é permitida")
    return a / b

if __name__ == "__main__":
    print("Calculadora")
    print(f"2 + 3 = {soma(2, 3)}")
    print(f"10 - 4 = {subtracao(10, 4)}")
    print(f"5 * 6 = {multiplicacao(5, 6)}")
    print(f"15 / 3 = {divisao(15, 3)}")
