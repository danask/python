#########################################
# print ("========== I/O ==============")
# inputName = ""
# inputName = input('Your name: ')

# print ("Your name is " + inputName)

# Q2. Password generater 
# http://www.google.com
# Rule#1. Remove "http://""
#         Remove the characters after the 2nd '.'
# Rule#2. the first 3 characters out of the rest of character 
#       + the number of characters 
#       + the number of 'o' 
#       + '!'
# ANS> goo62!

#webSite = "http://www.google.com"
webSite = input("Please input what you want to generate your password.\n" + "(e.g., http://www.yahoo.com)\n")
tempStr = webSite.replace("http://", "")
#print (tempStr)

firstIdxOfDot = tempStr.index('.') #tempStr.find('.') #3
#print (firstIdxOfDot)

secondIdxOfDot = tempStr.index('.', firstIdxOfDot + 1)
#print (secondIdxOfDot)

tempStr = tempStr[firstIdxOfDot + 1: secondIdxOfDot]

#print (tempStr)
print (tempStr[:3] + str(len(tempStr)) + str(tempStr.count('o')) + "!")
