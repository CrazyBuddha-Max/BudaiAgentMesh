import {useState} from 'react';
import {useNavigate} from 'react-router';
import {Card} from '@astryxdesign/core/Card';
import {VStack} from '@astryxdesign/core/VStack';
import {HStack} from '@astryxdesign/core/HStack';
import {Heading} from '@astryxdesign/core/Heading';
import {Text} from '@astryxdesign/core/Text';
import {TextInput} from '@astryxdesign/core/TextInput';
import {Button} from '@astryxdesign/core/Button';
import {Divider} from '@astryxdesign/core/Divider';
import {useToast} from '@astryxdesign/core/Toast';
import {api} from '@/api/client';
import {useAuthStore} from '@/store/auth';
import {Database} from 'lucide-react';

export function LoginPage() {
  const navigate = useNavigate();
  const toast = useToast();
  const setAuth = useAuthStore((s) => s.setAuth);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);

  const submit = async () => {
    if (!username || !password) {
      toast({body: '请输入用户名与密码', type: 'error'});
      return;
    }
    setLoading(true);
    try {
      const resp = await api.login(username, password);
      setAuth(resp.access_token, resp.user);
      navigate('/dashboard', {replace: true});
    } catch (err) {
      toast({body: err instanceof Error ? err.message : '登录失败', type: 'error'});
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-bg">
      <Card variant="muted" style={{width: 400, padding: 28}}>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void submit();
          }}
        >
          <VStack gap={5}>
            <VStack gap={1}>
              <HStack gap={2} vAlign="center">
                <Database size={22} />
                <Heading level={2}>BudaiAgentMesh</Heading>
              </HStack>
              <Text type="supporting">
                <span className="muted">智能体数据中台 · 统一接入 / 知识沉淀 / 协同治理</span>
              </Text>
            </VStack>

            <Divider />

            <TextInput
              label="用户名"
              type="text"
              value={username}
              onChange={(v) => setUsername(v)}
              isRequired
            />
            <TextInput
              label="密码"
              type="password"
              value={password}
              onChange={(v) => setPassword(v)}
              isRequired
            />

            <Button
              label={loading ? '登录中...' : '登录'}
              variant="primary"
              width="full"
              isLoading={loading}
              onClick={() => void submit()}
            />

            <VStack gap={1}>
              <Text type="supporting">
                <span className="muted">演示账号 (角色: 权限) </span>
              </Text>
              <Text type="supporting">
                <span className="mono">admin / admin123 (管理员)</span>
              </Text>
              <Text type="supporting">
                <span className="mono">analyst / analyst123 (分析师)</span>
              </Text>
              <Text type="supporting">
                <span className="mono">viewer / viewer123 (访客)</span>
              </Text>
            </VStack>
          </VStack>
        </form>
      </Card>
    </div>
  );
}
