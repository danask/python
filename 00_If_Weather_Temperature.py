#########################################
print ("\n ==== AI: What should I prepare today? ====\n")

#weather = "Sunny"
#temp = 10

weather = input("What is the weather like? (sunny, rainy, snowy) ")
temp = int(input("What temperature is now? ")) # I/O + casting

if weather == "rainy":
    print ("Bring your umbrella")
elif weather == "snowy":
    print ("Bring your mitts")
else:
    print ("Nothing to prepare")

if temp >= 30:
    print ("Too hot. Go to swimming pool or beach.")
elif 10 <= temp & temp <30: # and
    print ("Fine. Enjoy your day.")
elif 0 <= temp < 10:
    print ("Cold. Stay home.")
else:
    print ("Very cold. Sty home.")


# Assignment: Check your grade using your score.
# e.g., 
# 96 to 100: A+
# 91 to 95: A
# 86 to 90: B+
# 81 to 85: B
# 76 to 80: C+
# 71 to 75: C
# 0 to 70: D
