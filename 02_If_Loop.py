#########################################
print ("============ if ==============")

weather = "Sunny"
# weather = input("weather? (Sunny, Rainy, Snowy) ")

if weather == "Rainy":
    print ("Bring your umbrela")
elif weather == "Snowy":
    print ("Bring your mitts")
else:
    print ("Nothing to prepare")


temp = 10
# temp = int(input("Temperature? ")) # I/O + casting

if temp >= 30:
    print ("Too hot. Stay home")
elif 10 <= temp & temp <30: # and
    print ("Fine.")
elif 0 <= temp < 10:
    print ("Cold.")
else:
    print ("Very cold")


# Assignment: Check your grade using your score.
# e.g., 
# 96 to 100: A+
# 91 to 95: A
# 86 to 90: B+
# 81 to 85: B
# 76 to 80: C+
# 71 to 75: C
# 0 to 70: D


#########################################
print ("============ Loop ==============")

list = ["apple", "peach", "watermelon"]


for i in range(0, 3):       # range first (0 ~ 3)
    print(list[i])          # array next

count = 0
for val in list:            # for val in ["apple", "peach", "watermelon"]
    print(count, ":", val)
    count += 1              # i++

for val in list:
    print(val)
    if val.count("apple"):  # find -> return number
        print ("This is red fruit")
    elif val.count("peach"):
        print ("This is pink fruit")
    elif val.count("watermelon"):
        print ("This is green fruit")
    
customer = "IronMan"
index = 5

while index >= 1:
    print ("{0}, a missile is ready. {1} times left." .format(customer, str(index)))
    index -= 1

    if index == 0:
        print ("Nothing to use")


while True:
    print ("{0}, a missile is ready. {1} times left." .format(customer, str(index)))
    index += 1

    if index == 10:
        print ("Maximum number of missile")
        break






# Login


# attendance and mapping

absent = [2, 5, 9]

for student in range(1,9):
    if student in absent:
        continue
    print("{0} I'm here!" .format(student))


print ("----Attendance Check [Student ID: 1 to 9]----")
for student in range(1,9):
    if not(student in absent):
        print("{0} I'm here!" .format(student))


# 1 line for-loop
students = [10,2,30,4,50]
students = [val + 100 for val in students]
print(students)

# name to len
students = ["John", "Ted", "Daniel", "Mario"]
#students = [str(len(students[i])) for i in students] #wrong
students = [val.upper() for val in students]
print(students)

students = [len(val) for val in students]
print(students)


# Quiz
# Game Items which I can buy
# rule#1. 20 items
# rule#2. each items price: random number ($5 ~ 50)
# rule#3. My money: $10
# e.g, [X] item #1  ($10)
#      [ ] item #2  ($47)
#      ...
#      I can buy 3 item(s)

from random import *

myMoney = 10
count = 0
print("I have {0}." .format(myMoney))

for i in range (1,20):
    price = randint(5,51)
    if price <= myMoney:
        print("[X] item #{0} \t(${1})" .format(i, price))
        count += 1
    else:
        print("[ ] item #{0} \t(${1})" .format(i, price))

print("\nI can buy {0} item(s)" .format(count))




fruits = ["apple", "banana", "cherry"]
for i in range(len(fruits)): # 0, 1, 2
  print(fruits[i])

for i in range(0, 3): # 0, 1, 2
  print(fruits[i])

games = ["League Of Legend", "Starcraft", "Diablo 3", "Street Fighter", "Super Mario"]
prices = [10, 20, 35, 60, 80]

i = 0
while i < len(games):
    print (games[i][0] + "\t\t$" + str(prices[i]))
    i += 1

def sum():
    i = 0
    sum = 0
    while i <= 10:
        sum += i
        print(sum)
        i += 1


sum()

def even_numbers():
    i = 0
    while i <= 100:
        
        if i == 50:
            break
        
        if i % 2 == 0:
            print (i)
        
        i += 1

even_numbers()


def lotto_gen():
    i = 0
    while i < 6:
        print("Lotto Number" + str(i + 1), randint(1, 45)) # 1 to 45
        i += 1

lotto_gen()
from random import *

def lotto_gen():
    
    while True:
        ans = input("Generate Lotto number?(Y/N)")
        i = 0
        if ans == "y":
            while i < 6:
                print("Lotto Number" + str(i + 1), randint(1, 45)) # 1 to 45
                i += 1
        else:
            break
lotto_gen()

def make_grade():
    score = 0
    while score != -1:
        score = int(input("Enter your grade: "))

        if score > 95:
            print ("Your grade is A+. Congratulations!")
        elif score > 90:
            print ("Your grade is A. Exellent!")    
        elif score > 85:
            print ("Your grade is B+. Great.")    
        elif score > 80:
            print ("Your grade is B. Good.")        
        elif score > 75:
            print ("Your grade is C+.")        
        elif score > 70:
            print ("Your grade is C.")        
        elif score >= 0:
            print ("Your grade is D. Sorry.") 
# make_grade()


def man():
    response = "n"

    while response != "y":
        response = input("Are you a man (y/n)? ")
        if response != "Y" and response != "y":
            print("You're a robot. You're not permitted to enter")
        else:
            print("Confirmed. Pass the gate.")    
# man()


def multiple():

    while True:
        ans = int(input ("[Q] 10 + 100 = ?\n1) 10  2)100  3)110  4) 200\nEnter your answer: "))
        
        if ans == 3:
            print ("correct!")
            break
        else:
            print("wrong")

# multiple()

def dice_game():
    print ("\n --- Dice Game --- \n")
    myName = input("What is you name? ")
    inputVal = input("How many time do you want to play?(1 to 5) ")
    mySum = 0
    comSum = 0
    count = 0

    while count < int(inputVal):
    # if (inputVal == "y") | (inputVal == "Y"):
        input ("\nRoll your dice! (press enter)")
        myDiceScore = randint(1,6)
        print (myName + "'s score is " + str(myDiceScore))
        mySum += myDiceScore

        input ("\nComputer's dice (press enter)")
        comDiceScore = randint(1,6)
        print ("Computer's score is " + str(comDiceScore))
        comSum += comDiceScore

        count += 1

    input ("\nCheck the result of game!")
    print ("\n --- Result --- ")
    print ("You: " + str(mySum) + " vs. Computer: " + str(comSum))
    if mySum > comSum:
        print (myName + " wins!")
    elif mySum < comSum:
        print ("Computer wins!")
    else:
        print ("Tie!")

    input ("Thank you for playing!!")


# dice_game()