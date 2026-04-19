// Minimal smoke test: BT.CPP factory can parse the demo XML's structural
// subset and tick basic control-flow nodes. Skill-node registration and
// ROS action integration are covered by launch_testing in Phase 3.
#include <gtest/gtest.h>

#include <behaviortree_cpp/bt_factory.h>

TEST(BtFactoryTest, ParsesTrivialTree)
{
  const char * xml = R"(
    <root BTCPP_format="4">
      <BehaviorTree ID="Trivial">
        <AlwaysSuccess/>
      </BehaviorTree>
    </root>
  )";
  BT::BehaviorTreeFactory factory;
  auto tree = factory.createTreeFromText(xml);
  EXPECT_EQ(tree.tickOnce(), BT::NodeStatus::SUCCESS);
}

TEST(BtFactoryTest, SequenceOfSuccessNodes)
{
  const char * xml = R"(
    <root BTCPP_format="4">
      <BehaviorTree ID="Seq">
        <Sequence>
          <AlwaysSuccess/>
          <AlwaysSuccess/>
        </Sequence>
      </BehaviorTree>
    </root>
  )";
  BT::BehaviorTreeFactory factory;
  auto tree = factory.createTreeFromText(xml);
  EXPECT_EQ(tree.tickOnce(), BT::NodeStatus::SUCCESS);
}

TEST(BtFactoryTest, SequenceShortCircuitsOnFailure)
{
  const char * xml = R"(
    <root BTCPP_format="4">
      <BehaviorTree ID="SeqFail">
        <Sequence>
          <AlwaysFailure/>
          <AlwaysSuccess/>
        </Sequence>
      </BehaviorTree>
    </root>
  )";
  BT::BehaviorTreeFactory factory;
  auto tree = factory.createTreeFromText(xml);
  EXPECT_EQ(tree.tickOnce(), BT::NodeStatus::FAILURE);
}

int main(int argc, char ** argv)
{
  ::testing::InitGoogleTest(&argc, argv);
  return RUN_ALL_TESTS();
}
