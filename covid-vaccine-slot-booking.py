import requests
import datetime
import time
import winsound
import sys, msvcrt, tabulate, json, copy, argparse
from hashlib import sha256
from collections import Counter


CALENDAR_URL = "https://cdn-api.co-vin.in/api/v2/appointment/sessions/calendarByDistrict?district_id={0}&date={1}"
BOOKING_URL = "https://cdn-api.co-vin.in/api/v2/appointment/schedule"
BENEFICIARIES_URL = "https://cdn-api.co-vin.in/api/v2/appointment/beneficiaries"

WARNING_BEEP_DURATION = (1000, 2000)


def display_table(dict_list):
    header = ['idx'] + list(dict_list[0].keys())
    rows =  [[idx + 1] + list(x.values()) for idx, x in enumerate(dict_list)]
    print(tabulate.tabulate(rows, header, tablefmt='grid'))


class TimeoutExpired(Exception):
    pass


def check_calendar(request_header, vaccine_type, district_dtls, minimum_slots):
    try:
        print('===================================================================================')
        today = datetime.datetime.today()
        tomorrow = (today + datetime.timedelta(days=1)).strftime("%d-%m-%Y")
        
        CALENDAR_URL = "https://cdn-api.co-vin.in/api/v2/appointment/sessions/calendarByDistrict?district_id={0}&date={1}"

        if vaccine_type:
            CALENDAR_URL += f"&vaccine={vaccine_type}"
        
        options = []
        for district in district_dtls:
            resp = requests.get(CALENDAR_URL.format(district['district_id'], tomorrow), headers=request_header)
            
            if resp.status_code == 401:
                print('TOKEN INVALID')
                return False

            elif resp.status_code == 200:
                resp = resp.json()
                print(f"Centers available in {district['district_name']} from {tomorrow} as of {today.strftime('%Y-%m-%d %H:%M:%S')}: {len(resp['centers'])}")

                if len(resp['centers']) >= 0:
                    for center in resp['centers']:
                        out = {}
                        for session in center['sessions']:
                            if session['available_capacity'] >= minimum_slots:
                                out['name'] = center['name']
                                out['district'] = center['district_name']
                                out['center_id'] = center['center_id']
                                out['available'] = session['available_capacity']
                                out['date'] = session['date']
                                out['slots'] = session['slots']
                                out['session_id'] = session['session_id']
                                options.append(out)
                                winsound.Beep(district['district_alert_freq'], 150)
                            else:
                                pass
                else:
                    pass
            else:
                pass

        return options

    except Exception as e:
        print(str(e))
        winsound.Beep(WARNING_BEEP_DURATION[0], WARNING_BEEP_DURATION[1])


def book_appointment(request_header, details):
    try:
        print('================================= ATTEMPTING BOOKING ==================================================')
        
        resp = requests.post(BOOKING_URL, headers=request_header, json=details)
        print(f'Booking Response Code: {resp.status_code}')
        print(f'Booking Response : {resp.text}')

        if resp.status_code == 401:
            print('TOKEN INVALID')
            return False

        elif resp.status_code == 200:
            print('##############    BOOKED!  ##############')
            sys.exit(0)

        else:
            return True

    except Exception as e:
        print(str(e))
        winsound.Beep(1000, 2000)


def input_with_timeout(prompt, timeout, timer=time.monotonic):
    sys.stdout.write(prompt)
    sys.stdout.flush()
    endtime = timer() + timeout
    result = []
    while timer() < endtime:
        if msvcrt.kbhit():
            result.append(msvcrt.getwche()) #XXX can it block on multibyte characters?
            if result[-1] == '\r':
                return ''.join(result[:-1])
        time.sleep(0.04) # just to yield to other processes/threads
    raise TimeoutExpired


def check_and_book(request_header, vaccine_type, beneficiary_dtls, district_dtls, minimum_slots):
    try:
        options = check_calendar(request_header, vaccine_type, district_dtls, minimum_slots)

        if isinstance(options, bool):
            return False
        
        tmp_options = copy.deepcopy(options)
        if len(tmp_options) > 0:
            cleaned_options_for_display = []
            for item in tmp_options:
                item.pop('session_id', None)
                item.pop('center_id', None)
                cleaned_options_for_display.append(item)

            display_table(cleaned_options_for_display)
            choice = input_with_timeout('----------> \nWait 10 seconds for updated options OR \n----------> \nEnter a choice e.g: 1.4 for (1st center 4th slot): ', 10)

        else:
            print("No viable options. Waiting for next update in 15s.")
            time.sleep(15)
            choice = '.'
        
    
    except TimeoutExpired:
        time.sleep(15)
        return True
    
    else:
        if choice == '.':
            return True
        else:
            choice = choice.split('.')
            choice = [int(item) for item in choice]
            print(f'============> Got {choice}')
            
            new_req = {}
            beneficiaries = [beneficiary['beneficiary_reference_id'] for beneficiary in beneficiary_dtls]
            new_req['beneficiaries'] = beneficiaries                             # pass list of beneficiaries
            new_req['dose'] = 2 if vaccine_type else 1                           # if vaccine type is available, then its their second dose
            new_req['center_id'] = options[choice[0] - 1]['center_id']
            new_req['session_id'] = options[choice[0] - 1]['session_id']
            new_req['slot'] = options[int(choice[0]) - 1]['slots'][choice[1] - 1]
            print(f'Booking with info: {new_req}')

            return book_appointment(request_header, new_req)


def get_districts(request_header):
    states = requests.get('https://cdn-api.co-vin.in/api/v2/admin/location/states')

    state = None
    if states.status_code == 200:
        states = states.json()['states']
        
        refined_states = []
        for state in states:
            tmp = {}
            tmp['state'] = state['state_name']
            refined_states.append(tmp)
        
        display_table(refined_states)

        state = int(input('Enter State index: '))
        state_id = states[state - 1]['state_id']

    else:
        print('Unable to fetch states')
        print(states.status_code)
        print(states.text)
        sys.exit(1)

    districts = requests.get(f'https://cdn-api.co-vin.in/api/v2/admin/location/districts/{state_id}')
    if districts.status_code == 200:
        districts = districts.json()['districts']
        
        refined_districts = []
        for district in districts:
            tmp = {}
            tmp['district'] = district['district_name']
            refined_districts.append(tmp)
        
        display_table(refined_districts)
        reqd_districts = input('Enter comma separated index numbers of districts to monitor : ')
        districts_idx = [int(idx) -1 for idx in reqd_districts.split(',')]
        reqd_districts = [{
            'district_id': item['district_id'], 
            'district_name': item['district_name'],
            'district_alert_freq': 440 + ((2 * idx) * 110)
            } for idx, item in enumerate(districts) if idx in districts_idx]
        
        print(f'Selected districts: ')
        display_table(reqd_districts)
        return reqd_districts


    else:
        print('Unable to fetch districts')
        print(districts.status_code)
        print(districts.text)
        sys.exit(1)


def get_beneficiaries(request_header):
    beneficiaries = requests.get(BENEFICIARIES_URL, headers=request_header)

    if beneficiaries.status_code == 200:
        beneficiaries = beneficiaries.json()['beneficiaries']
        
        refined_beneficiaries = []
        for beneficiary in beneficiaries:
            tmp = {}
            tmp['beneficiary_reference_id'] = beneficiary['beneficiary_reference_id']
            tmp['name'] = beneficiary['name']
            tmp['vaccine'] = beneficiary['vaccine']
            refined_beneficiaries.append(tmp)
        
        display_table(refined_beneficiaries)
        print("""
        ################# IMPORTANT NOTES ################# 
        # 1. While selecting beneficiaries, make sure that selected beneficiaries are all taking the same dose: either first OR second.
        #    Please do no try to club together booking for first dose for one beneficiary and second dose for another beneficiary.
        # 
        # 2. While selecting beneficiaries, also make sure that beneficiaries selected for second dose are all taking the same vaccine: COVISHIELD OR COVAXIN.
        #    Please do no try to club together booking for beneficiary taking COVISHIELD with beneficiary taking COVAXIN.
        ###################################################
        """)
        reqd_beneficiaries = input('Enter comma separated index numbers of beneficiaries to book for : ')
        beneficiary_idx = [int(idx) -1 for idx in reqd_beneficiaries.split(',')]
        reqd_beneficiaries = [{
            'beneficiary_reference_id': item['beneficiary_reference_id'], 
            'vaccine': item['vaccine']
            } for idx, item in enumerate(beneficiaries) if idx in beneficiary_idx]

        
        print(f'Selected beneficiaries: ')
        display_table(reqd_beneficiaries)
        return reqd_beneficiaries

    else:
        print('Unable to fetch beneficiaries')
        print(beneficiaries.status_code)
        print(beneficiaries.text)
        sys.exit(1)


def generate_token_OTP(mobile):
    data = {"mobile": mobile, "secret": "U2FsdGVkX1/3I5UgN1RozGJtexc1kfsaCKPadSux9LY+cVUADlIDuKn0wCN+Y8iB4ceu6gFxNQ5cCfjm1BsmRQ=="}
    print(f"Requesting OTP with mobile number {mobile}..")
    txnId = requests.post(url='https://cdn-api.co-vin.in/api/v2/auth/generateMobileOTP', json=data)
    
    if txnId.status_code == 200:
        txnId = txnId.json()['txnId']
    else:
        print('Unable to Create OTP')
        print(txnId.text)
        sys.exit(1)

    OTP = input("Enter OTP: ")
    data = {"otp": sha256(str(OTP).encode('utf-8')).hexdigest(), "txnId": txnId}
    print(f"Validating OTP..")

    token = requests.post(url='https://cdn-api.co-vin.in/api/v2/auth/validateMobileOtp', json=data)
    if token.status_code == 200:
        token = token.json()['token']
    else:
        print('Unable to Validate OTP')
        print(token.text)
        sys.exit(1)
    
    print(f'Token Generated: {token}')
    return token
    

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--mobile', help='Pass the registered mobile to generate OTP')
    parser.add_argument('--token', help='Pass token directly')
    args = parser.parse_args()

    token = None
    mobile = args.mobile
    if args.token:
        token = args.token
    elif mobile:
        token = generate_token_OTP(mobile)
    
    request_header = {"Authorization": f"Bearer {token}"}

    print("Fetching registered beneficiaries.. ")
    beneficiary_dtls = get_beneficiaries(request_header)
    assert len(beneficiary_dtls) > 0, "There should be at least one beneficiary"

    vaccine_types = [beneficiary['vaccine'] for beneficiary in beneficiary_dtls]
    vaccines = Counter(vaccine_types)
    assert len(vaccines.keys()) == 1, f"All beneficiaries in one attempt should have the same vaccine type. Found {len(vaccines.keys())}"
    vaccine_type = vaccine_types[0]

    district_dtls = get_districts(request_header)
    minimum_slots = int(input('Filter out centers with availability less than: '))
    minimum_slots = minimum_slots if minimum_slots > len(beneficiary_dtls) else len(beneficiary_dtls)

    TOKEN_VALID = True
    while TOKEN_VALID:
        request_header = {"Authorization": f"Bearer {token}"}
        
        TOKEN_VALID = check_and_book(request_header, vaccine_type, beneficiary_dtls, district_dtls, minimum_slots)
        
        beneficiaries_list = requests.get(BENEFICIARIES_URL, headers=request_header)
        if beneficiaries_list.status_code == 200:
            TOKEN_VALID = True
        
        else:
            winsound.Beep(WARNING_BEEP_DURATION[0], WARNING_BEEP_DURATION[1])
            print('Token is INVALID.')
            TOKEN_VALID = False

            tryOTP = input('Try for a new Token? (y/n): ')
            if tryOTP.lower() == 'y':
                if mobile:
                    tryOTP = input(f"Try for OTP with mobile number {mobile}? (y/n) : ")
                    if tryOTP.lower() == 'y':
                        token = generate_token_OTP(mobile)
                        TOKEN_VALID = True
                    else:
                        TOKEN_VALID = False
                        print("Exiting")
                else:
                    mobile = input(f"Enter 10 digit mobile number for new OTP generation? : ")
                    token = generate_token_OTP(mobile)
                    TOKEN_VALID = True
            else:
                print("Exiting")
                sys.exit()

if __name__ == '__main__':
    main()