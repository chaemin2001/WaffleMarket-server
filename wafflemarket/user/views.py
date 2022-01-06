from django.contrib.auth import authenticate, login, logout, get_user_model
from django.db import IntegrityError
from rest_framework import serializers, status, viewsets, permissions
from rest_framework.views import APIView
from rest_framework.decorators import action
from rest_framework.response import Response
from .serializers import UserLoginSerializer, UserCreateSerializer,  UserAuthSerializer, UserSerializer, UserUpdateSerializer

import requests
from django.core.exceptions import ValidationError
from google.oauth2 import id_token
from google.auth.transport.requests import Request
import os
import wafflemarket.settings as settings
from django.shortcuts import render
from django.http import HttpResponse

User = get_user_model()

def login(data):
    serializer = UserLoginSerializer(data=data)
    first_login = serializer.check_first_login(data=data)
    location_exists = serializer.location_exists(data=data)
    serializer.is_valid(raise_exception=True)
                
    phone_number = serializer.validated_data.get('phone_number')
    email = serializer.validated_data.get('email')
    username = serializer.validated_data.get('username')
    token = serializer.validated_data.get('token')
    return {
    'phone_number': phone_number,
    'email': email,
    'username' : username,
    'logined': True, 
    'first_login' : first_login, 
    'location_exists' : location_exists, 
    'token' : token
    }

class UserAuthView(APIView):
    permission_classes = (permissions.AllowAny, )
        
    def post(self, request):
        serializer = UserAuthSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        auth = serializer.save()
        return Response(data={'phone_number': auth.phone_number, 'auth_number': auth.auth_number},
                        status=status.HTTP_200_OK)
        
    def put(self, request):
        serializer = UserAuthSerializer(data=request.data)
        if serializer.authenticate(data=request.data):
            if User.objects.filter(phone_number=request.data['phone_number']).exists():
                return Response(login(request.data), status=status.HTTP_200_OK)
            else:
                return Response(data={'authenticated': True, 'phone_number': request.data['phone_number']},status=status.HTTP_200_OK)
        else:
            return Response(data='인증번호가 일치하지 않습니다.', status=status.HTTP_400_BAD_REQUEST)
    
class UserSignUpView(APIView):
    permission_classes = (permissions.AllowAny, )
    def post(self, request, *args, **kwargs):
        serializer = UserCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            user, jwt_token = serializer.save()
        except IntegrityError:
            return Response(login(request.data), status=status.HTTP_200_OK)
        return Response(login(request.data), status=status.HTTP_201_CREATED)

class GoogleSigninCallBackApi(APIView):
    permission_classes = (permissions.AllowAny, )

    def get(self, request, *args, **kwargs):
        if settings.DEBUG:
            return render(request, 'user/logintest.html')
        else:
            return HttpResponse(status=404)

    def post(self, request, *args, **kwargs):
        token = request.data.get('token')
        
        # verifying access_token
        try:
            idinfo = id_token.verify_oauth2_token(token, Request(), os.getenv('GOOGLE_CLIENT_ID'))
            userid = idinfo['sub']
        except ValueError:
            pass

        # request google to get user info
        user_info_response = requests.get(
            "https://oauth2.googleapis.com/tokeninfo",
            params={ 'id_token': token }
        )
        if not user_info_response.ok:
            raise ValidationError('Failed to obtain user info from Google.')
        user_info = user_info_response.json()
        
        username = user_info.get('family_name', '')+user_info.get('given_name', '')
        username = username.replace(' ', '').replace('\xad', '')
        profile_data = {
            'email': user_info['email'],
            'username': username,
            'profile_image': user_info.get('picture', None)
        }
        
        # signup or login with given info
        serializer = UserCreateSerializer(data=profile_data)
        serializer.is_valid(raise_exception=True)
        try:
            user, jwt_token = serializer.save()
        except IntegrityError:
            return Response(login(profile_data), status=status.HTTP_200_OK)
        return Response(login(profile_data), status=status.HTTP_201_CREATED)

    
class UserLogoutView(APIView):
    permission_classes = (permissions.IsAuthenticated, )
    
    def post(self, request):
        logout(request)
        return Response({'logined': False}, status=status.HTTP_200_OK)
    
class UserLeaveView(APIView):
    permission_classes = (permissions.IsAuthenticated, )

    def delete(self, request):
        #우선 임시탈퇴를 영구탈퇴로 변경하여 구현함
        '''request.user.is_active = False
        request.user.save()
        logout(request)'''
        request.user.delete()
        return Response(data={'leaved': True}, status=status.HTTP_200_OK)
    
class UserViewSet(viewsets.GenericViewSet): 
    permission_classes = (permissions.IsAuthenticated, )
    serializer_class = UserSerializer
    queryset = User.objects.all()
    
    def list(self, request):
        user = request.user
        return Response(self.get_serializer(user).data, status=status.HTTP_200_OK)
    
    def put(self, request):
        user = request.user
        serializer = UserUpdateSerializer(user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.check_username({'data' : serializer.validated_data, 'user' : request.user})
        user = serializer.update(user, serializer.validated_data)
        
        try:
            profile_image = request.FILES['profile_image']
            user.profile_image = profile_image
            user.save()
        except:
            pass
        return Response(self.get_serializer(user).data, status=status.HTTP_200_OK)