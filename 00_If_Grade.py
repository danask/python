#########################################
print ("\n ==== What is my grade? ====\n")
# Assignment: Check your grade using your score.
# e.g., 
# 96 to 100: A+
# 91 to 95: A
# 86 to 90: B+
# 81 to 85: B
# 76 to 80: C+
# 71 to 75: C
# 0 to 70: D

# score = int(input("Enter your grade: "))
   



while True:
    multiple = input("[Q] 10 + 100 = \n1)10\t2)100\t3)110\t4)200" +
                "\nWhat is the sum of 10 and 100? " )    
    if multiple == "1" or multiple == "2":
         print ("The correct answer higher than your answer")
    elif multiple == "4":
         print ("The correct answer is less than your answer")
    else:
         print ("Your answer is correct") 
         break
