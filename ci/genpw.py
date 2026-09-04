#!/usr/bin/env python3
"""보드 비밀번호 생성기.

흔한 영어 단어 6개를 난수로 골라 잇는다. 특수문자·대문자를 섞는 것보다
'평범한 단어를 여러 개'가 오프라인 공격에 훨씬 강하고, 사람이 쓰기도 쉽다.

  python3 genpw.py        # 5개 후보
  python3 genpw.py 8      # 8개 후보
"""
import math, secrets, sys

W = """apple table river cloud green stone light water paper mouse tiger horse music
paint chair bread grape happy quiet sunny north south smile ocean forest window
garden silver golden purple orange yellow summer winter spring autumn candle
basket bridge circle coffee cookie dragon flower guitar hammer island jacket
kitten ladder lemon magnet needle orbit pencil pillow rabbit rocket saddle
shadow socket spider spoon square street sugar sunset temple ticket tunnel
turtle violet wagon walnut wallet whale wheat willow yogurt zebra anchor animal
arrow bamboo banana barrel beacon beetle bottle branch butter button camera
canvas carpet carrot castle cattle cherry cotton cradle crayon desert dinner
donkey engine fabric falcon feather fiddle finger flame fossil frozen galaxy
garlic ginger glove hamster harbor helmet honey hunter jungle kettle lantern
laptop lizard lobster locker maple marble market meadow melody mirror monkey
muffin napkin nectar noodle olive onion otter oyster palace panda parrot peanut
pepper piano pigeon pillar planet pocket potato puppy puzzle quilt radish
raisin ribbon robin rubber salmon sandal school shrimp signal singer sketch
soup sparrow spinach squash stable statue stove studio subway sweater sword
syrup tablet teapot thread thunder timber tomato torch towel tractor trumpet
tulip turkey valley vanilla velvet village violin voyage waffle walrus weasel
whisker whistle wisdom wizard wonder wooden zipper acorn album alley almond
amber apron arcade artist attic bakery balcony ballet banner barley beach
beaver biscuit blanket blossom bonfire boulder breeze brick brush bubble
buffalo bunny burrow cabin cactus canyon caramel cascade cavern cedar celery
cello chalk cheese chimney clover cobweb comet compass coral cottage coyote
crane cricket crown cucumber cupcake curtain cushion cymbal dagger daisy
dolphin domino doodle dough dove eagle echo eclipse elbow elder elephant
ember emerald"""

WORDS = sorted(set(W.split()))
N_WORDS = 6                                  # 5개로 줄이면 강도가 크게 떨어진다

def main(count):
    bits = N_WORDS * math.log2(len(WORDS))
    years = (2 ** bits / 2) / 16000 / 60 / 60 / 24 / 365   # PBKDF2 31만 회 · GPU 1장 추정
    print(f'단어 풀 {len(WORDS)}개 · {N_WORDS}단어 · 약 {bits:.0f}비트')
    print(f'오프라인 공격 추정: GPU 1장 {years:,.0f}년 · 1,000장 {years/1000:,.1f}년\n')
    for _ in range(count):
        print('  ' + '-'.join(secrets.choice(WORDS) for _ in range(N_WORDS)))
    print('\n하나를 골라 GitHub 시크릿 BOARD_PASSWORD 에 넣고 refresh 를 실행하세요.')
    print('고른 값은 어디에도(대화창 포함) 붙여넣지 마세요.')

if __name__ == '__main__':
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 5)
