from django.contrib.auth.hashers import check_password, make_password
from django.core.cache import cache
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.mixins import (CreateModelMixin, DestroyModelMixin,
                                   ListModelMixin, RetrieveModelMixin,
                                   UpdateModelMixin)
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import GenericViewSet, ModelViewSet

from rest_framework_simplejwt.tokens import RefreshToken
from utils.queryset import get_child_queryset

from .models import Organization, Permission, Position, Role, User, DictType, Dict
from .permission import RbacPermission, get_permission_list
from .serializers import (OrganizationSerializer, PermissionSerializer,
                          PositionSerializer, RoleSerializer,
                          UserCreateSerializer, UserListSerializer,
                          UserModifySerializer, DictSerializer, DictTypeSerializer)
from .filters import UserFilter
import logging

logger = logging.getLogger('log')
# logger.info('请求成功！ response_code:{}；response_headers:{}；response_body:{}'.format(response_code, response_headers, response_body[:251]))
# logger.error('请求出错：{}'.format(error))


class LogoutView(APIView):
    permission_classes = []

    def get(self, request, *args, **kwargs):  # 可将token加入黑名单
        return Response(status=status.HTTP_200_OK)

class DictTypeViewSet(ModelViewSet):
    """
    数据字典类型：增删改查
    """
    perms_map = [{'post': 'dicttype_create'},
                 {'put': 'dicttype_update'},
                 {'delete': 'dicttype_delete'},
                 {'get': 'dicttype_view'},
                 ]
    queryset = DictType.objects.all()
    serializer_class = DictTypeSerializer
    pagination_class = None
    search_fields = ['^name']
    ordering_fields = ['id']
    ordering = 'id'


class DictViewSet(ModelViewSet):
    """
    数据字典：增删改查
    """
    perms_map = [{'post': 'dict_create'},
                 {'put': 'dict_update'},
                 {'delete': 'dict_delete'},
                 {'get': 'dict_view'},
                 ]
    queryset = Dict.objects.all()
    serializer_class = DictSerializer
    search_fields = ['^name']
    ordering_fields = ['id']
    ordering = 'id'

class PositionViewSet(ModelViewSet):
    """
    岗位：增删改查
    """
    perms_map = [{'post': 'position_create'},
                 {'put': 'position_update'},
                 {'delete': 'position_delete'},
                 {'get': 'position_view'},
                 ]
    queryset = Position.objects.all()
    serializer_class = PositionSerializer
    pagination_class = None
    search_fields = ['^name']
    ordering_fields = ['id']
    ordering = 'id'


class TestView(APIView):
    perms_map = [{'get': 'test_view'}]  # 单个API控权
    pass


class PermissionViewSet(ModelViewSet):
    """
    权限：增删改查
    """
    perms_map = [{'post': 'perm_create'},  # 视图类控权
                 {'put': 'perm_update'},
                 {'delete': 'perm_delete'},
                 {'get': 'perm_view'},
                 ]
    queryset = Permission.objects.all()
    serializer_class = PermissionSerializer
    pagination_class = None
    search_fields = ['name']
    ordering_fields = ['sort']
    ordering = 'id'


class OrganizationViewSet(ModelViewSet):
    """
    组织机构：增删改查
    """
    perms_map = [{'post': 'org_create'},
                 {'put': 'org_update'},
                 {'delete': 'org_delete'},
                 {'get': 'org_view'},
                 ]
    queryset = Organization.objects.all()
    serializer_class = OrganizationSerializer
    pagination_class = None
    search_fields = ['^name']
    ordering_fields = ['id']
    ordering = 'id'


class RoleViewSet(ModelViewSet):
    """
    角色：增删改查
    """
    perms_map = [{'post': 'role_create'},
                 {'put': 'role_update'},
                 {'delete': 'role_delete'},
                 {'get': 'role_view'},
                 ]
    queryset = Role.objects.all()
    serializer_class = RoleSerializer
    pagination_class = None
    search_fields = ['name']
    ordering_fields = ['id']
    ordering = 'id'


class UserViewSet(ModelViewSet):
    """
    用户管理：增删改查
    """
    perms_map = [{'post': 'user_create'},
                 {'put': 'user_update'},
                 {'delete': 'user_delete'},
                 {'get': 'user_view'},
                 ]
    queryset = User.objects.all().order_by('-id')
    serializer_class = UserListSerializer
    filterset_class = UserFilter
    search_fields = ['username', 'name', 'phone', 'email']
    ordering_fields = ['-id']

    def get_queryset(self):
        queryset = self.queryset
        queryset = self.get_serializer_class().setup_eager_loading(queryset)  # 性能优化
        dept = self.request.query_params.get('dept', None)  # 该部门及其子部门所有员工
        if dept is not None:
            deptqueryset = get_child_queryset('rbac.Organization', dept)
            queryset = queryset.filter(dept__in=deptqueryset)
        return queryset

    def get_serializer_class(self):
        # 根据请求类型动态变更serializer
        if self.action == 'create':
            return UserCreateSerializer
        elif self.action == 'list':
            return UserListSerializer
        return UserModifySerializer

    def create(self, request, *args, **kwargs):
        # 创建用户默认添加密码
        password = request.data['password'] if 'password' in request.data else None
        if password:
            request.data['password'] = make_password(password)
        else:
            request.data['password'] = make_password('0000')
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return Response(serializer.data)

    @action(methods=['put'], detail=True, permission_classes=[IsAuthenticated],
            url_name='change_password')
    def password(self, request, pk=None):
        """
        修改密码
        """
        user = User.objects.get(id=pk)
        old_password = request.data['old_password']
        if check_password(old_password, user.password):
            new_password1 = request.data['new_password1']
            new_password2 = request.data['new_password2']
            if new_password1 == new_password2:
                user.set_password(new_password2)
                user.save()
                return Response('密码修改成功!', status=status.HTTP_200_OK)
            else:
                return Response('新密码两次输入不一致!', status=status.HTTP_400_BAD_REQUEST)
        else:
            return Response('旧密码错误!', status=status.HTTP_400_BAD_REQUEST)

    # perms_map=[{'get':'my_info'}], 自定义action控权
    @action(methods=['get'], detail=False, url_name='my_info', permission_classes=[IsAuthenticated])
    def info(self, request, pk=None):
        """
        初始化用户信息
        """
        user = request.user
        perms = get_permission_list(user)
        data = {
            'id': user.id,
            'username': user.username,
            'name': user.name,
            'roles': user.roles.all().values_list('name', flat=True),
            # 'avatar': request._request._current_scheme_host + '/media/' + str(user.image),
            'avatar': user.avatar,
            'perms': perms,
        }
        return Response(data)
