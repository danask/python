#########################################
# Basic: Setup, Var Type, print (\t\n), comment, cast

print(-10*(11 + 2));
print(-10.13 + 1);
print("asdf  " + str(2*12) + ' a,'*3); # cast
print(not (5>10));
print(not True);

age = 5;
name = "Dan";
is_adult = age >= 10;

'''
comment
multiple lines
'''

#if is_adult:
print("Hello, "+ name + " an adult " + str(is_adult) + "\n") # no indent
#else:
print("Hello, ", name, " is ", "a student ", not(is_adult), "\n")


# E0. Setup, Execute py, Hello World

# E1. Print your name
# E2. Print your age
# E3. Print your name and age
# E4. Make variables: 4 types
# E5. Print you are adult

# E6. Add comments
# E7. Print types
# E8. Print with \n \t


# Quiz 1. Use variables and print the sentences.

# variable: subject
# value: "English", "Math", "Computer"

# print: "I like 'Math"
subject = "Math"

print (type(subject))
print ("I like " + subject)

# Quiz 2. Make sentences
# Twinkle, twinkle, little star,
# 	How I wonder what you are! 
# 		Up above the world so high,   		
# 		Like a diamond in the sky. 
# Twinkle, twinkle, little star, 
# 	How I wonder what you are

print("Twinkle, twinkle, little star, \n" +
"\tHow I wonder what you are! \n" +
"\t\tUp above the world so high, \n" +
"\t\tLike a diamond in the sky. \n" +
"Twinkle, twinkle, little star, \n" + 
"\tHow I wonder what you are!")



#########################################
# Math operator

print(2**3) # 2^3 = 8 
print(pow(2,3))

print(10 % 3) # 1 (remainder)
print(10 // 3) # 3 (quotient)
print(10 / 3) # 3.3333

# && -> & / and
# || -> | / or

print(5 <= 5) # True
print(not(2 + 3 != 5)) # True

print(5 > 4 and 4 > 3) # True
print(5 > 4 & 4 > 3) # True
print(5 > 4 or 4 > 3) # True
print(5 > 4 | 4 > 3) # True

print(5 > 4 > 7) # False

a = 10
a += 5
a %= 2
print ("mode:",a)

print(min(100, 1000))
print(abs(-5)) #5
print("round 3.145: ", (round(3.145)))
print("round 3.5: ", (round(3.5)))

# max, abs, round

from math import *
from random import *

print(floor(4.99)) # round down
print(ceil(3.14)) # round up
print(sqrt(16)) # 4
print("Random:" + str(random() * 10)) # 0.0 ~ 10.0
print("Random:" + str(int(random() * 10)+1)) # 1 ~ <= 10
print("randint:" + str(randint(1,10)))

#EX. Dice game

# print ("\n --- Dice Game --- \n")
# myName = input("What is you name? ")
# inputVal = input("How many time do you want to play?(1 to 5) ")
# mySum = 0
# comSum = 0
# count = 0

# while count < int(inputVal):
# # if (inputVal == "y") | (inputVal == "Y"):
#     input ("\nRoll your dice! (press enter)")
#     myDiceScore = randint(1,6)
#     print (myName + "'s score is " + str(myDiceScore))
#     mySum += myDiceScore

#     input ("\nComputer's dice (press enter)")
#     comDiceScore = randint(1,6)
#     print ("Computer's score is " + str(comDiceScore))
#     comSum += comDiceScore

#     count += 1

# input ("\nCheck the result of game!")
# print ("\n --- Result --- ")
# print ("You: " + str(mySum) + " vs. Computer: " + str(comSum))
# if mySum > comSum:
#     print (myName + " wins!")
# elif mySum < comSum:
#     print ("Computer wins!")
# else:
#     print ("Tie!")

# input ("Thank you for playing!!")

# Q2. Lotto 
print("Lotto Number1", int(random() * 45) + 1) # 1 to 45
print("Lotto Number2", randrange(1,46)) # 1 to 45
print("Lotto Number3", randint(1, 45)) # 1 to 45
print("Lotto Number4", int(random() * 45) + 1)
print("Lotto Number5", randrange(1,46))
print("Lotto Number6", randint(1, 45))

# Q2. meeting date with var: 1) random date, 2) 1~3 X, 3) <28
date = str(randint(4, 28))
print ("Class opens " + date + ", July")



#########################################
print ("========== String ==============")
a = 'ab\\c'
b = "defg\n"
c = """-----------
================
"""

print (a, b, c)

phoneNumber = "A23-B56-B890" #0
print ('size:', len(phoneNumber))

# first
print ("phoneNumber: first -> " + phoneNumber[:3])
print ("phoneNumber: first -> " + phoneNumber[-(len(phoneNumber)):3])

# second
currentIdx = phoneNumber.index("B")
print ("2nd B's pos:", phoneNumber.index("B", currentIdx + 1)) # idx of next "B"
print ("phoneNumber: middle -> " + phoneNumber[4:7])
print(phoneNumber.split('-')[1])

# thrid
print ("phoneNumber: last -> " + phoneNumber[8:])
print ("phoneNumber: last -> " + phoneNumber[-4:]) # from end, reversely

print(phoneNumber.replace('-', '.'))
print(phoneNumber.lower())
print(phoneNumber[0].isalpha())

# if no exist, index -> error, find -> -1
print("contains('B89') -> %d" % phoneNumber.find('B89'))
print("\ncontains('1') -> %d" % phoneNumber.find('1'))

print(phoneNumber.count("B"))
print("I am %s, %d" % ("Daniel", 100)) # no comma
print("I am {}, {}" .format("Daniel", 100)) 
print("I am {1}, {0}" .format("Daniel", 100)) 
print("I am {name}, {age}" .format(name = "Daniel", age = 100)) # JSON style
print(f"My phone number is {phoneNumber}")

print("abc def \r123")
print("abc def \b123")
print("abc\tdef\t123")

# Q1. Word Count and Replacement
# A robot was created by man. But even if I had a robot that knew everything, I couldn't really say, "Tell me every custom they have here" and be fully informed. No human can solder a billion transistors on a computer processor, so your computer needed a robot in order to be built. Instead, it is a large, open-air farm with a robot assigned to make each turnip be all that it can be.

essay = "A robot was created by man. But even if I had a robot that knew everything, I couldn't really say, Tell me every custom they have here and be fully informed. No human can solder a billion transistors on a computer processor, so your computer needed a robot in order to be built. Instead, it is a large, open-air farm with a robot assigned to make each turnip be all that it can be."
print ("count of robot: ", essay.count("robot"))
essay = essay.replace("robot", "AI")
print (essay)

# Q2. Password generater 
# http://www.google.com
# Rule#1. Remove "http://""
#         Remove the characters after the 2nd '.'
# Rule#2. the first 3 characters out of the rest of character 
#       + the number of characters 
#       + the number of 'o' 
#       + '!'
# ANS> goo62!

webSite = "http://www.google.com.test"
# webSite = input("Please input what you want to generate your password.\n")
tempStr = webSite.replace("http://", "")
print (tempStr)

firstIdxOfDot = tempStr.index('.') #tempStr.find('.') #3
print ("1st:", firstIdxOfDot)

secondIdxOfDot = tempStr.index('.', firstIdxOfDot + len(".")) # search from current idx + len(.): starting idx
print ("2nd:", secondIdxOfDot)

thirdIdxOfDot = tempStr.index('.', secondIdxOfDot + len("."))
print ("3nd:", thirdIdxOfDot)

tempStr = tempStr[firstIdxOfDot + 1: secondIdxOfDot]

print (tempStr)
print (tempStr[:3] + str(len(tempStr)) + str(tempStr.count('o')) + "!")


# comp_data = 'aaa.bbb.ccc.bbb.ccc.bbb' 
# index = 0 

# while index > -1: 
#     index = comp_data.find('bbb', index) 
#     if index != -1: 
#         print(index) 
#         index += len('bbb')


currentIdx = phoneNumber.index("B")
print(currentIdx)

nextIdx = phoneNumber.index("B", currentIdx + len("B"))
print(nextIdx)
